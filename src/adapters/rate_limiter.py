"""Per-domain rate limiter con jitter y backoff exponencial.

Objetivo:
- Prevenir comportamiento DoS-adyacente al escanear cientos de sitios.
- Respetar la infraestructura de las plataformas escaneadas.
- Mejorar la precisión del escaneo evitando 429/503 por abuso.

Diseño:
- Un semáforo *por dominio* (hostname) limita requests concurrentes al mismo origen.
- Un delay mínimo + jitter temporal entre requests al mismo dominio.
- Retry con backoff exponencial y parsing de Retry-After en 429/503.
"""

from __future__ import annotations

import asyncio
import random
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from email.utils import parsedate_to_datetime
from typing import AsyncIterator
from urllib.parse import urlparse

import httpx


# ---------------------------------------------------------------------------
# Domain extraction
# ---------------------------------------------------------------------------

def extract_domain(url: str) -> str:
    """Extrae el hostname del URL para agrupar por dominio.

    Usa hostname directo (no eTLD+1) para evitar dependencias externas.
    Esto cubre el 95%+ de los casos en site-lists OSINT.
    """
    try:
        parsed = urlparse(url)
        return (parsed.hostname or "unknown").lower()
    except Exception:
        return "unknown"


# ---------------------------------------------------------------------------
# Retry-After parsing
# ---------------------------------------------------------------------------

def parse_retry_after(header_value: str | None) -> float | None:
    """Parsea el header Retry-After (segundos o HTTP-date).

    Returns el número de segundos a esperar, o None si no es parseable.
    """
    if not header_value:
        return None

    # Intentar como número de segundos
    try:
        seconds = float(header_value)
        if seconds >= 0:
            return min(seconds, 120.0)  # Cap de seguridad: máximo 2 minutos
        return None
    except ValueError:
        pass

    # Intentar como HTTP-date (RFC 7231)
    try:
        retry_date = parsedate_to_datetime(header_value)
        delta = (retry_date.timestamp() - time.time())
        if delta > 0:
            return min(delta, 120.0)
        return 0.0
    except Exception:
        return None


# ---------------------------------------------------------------------------
# DomainRateLimiter
# ---------------------------------------------------------------------------

class DomainRateLimiter:
    """Rate limiter por dominio con jitter y backoff.

    Parámetros:
        per_domain_concurrency: Máx. requests simultáneos al mismo dominio.
        delay_ms:               Delay mínimo (ms) entre requests al mismo dominio.
        jitter_ms:              Jitter ± (ms) añadido al delay.
        retry_max_attempts:     Máx. reintentos en 429/503.
    """

    def __init__(
        self,
        *,
        per_domain_concurrency: int = 3,
        delay_ms: int = 200,
        jitter_ms: int = 100,
        retry_max_attempts: int = 3,
    ) -> None:
        self._per_domain_concurrency = max(1, per_domain_concurrency)
        self._delay_s = max(0, delay_ms) / 1000.0
        self._jitter_s = max(0, jitter_ms) / 1000.0
        self._retry_max = max(0, retry_max_attempts)

        # Estado por dominio
        self._domain_sems: dict[str, asyncio.Semaphore] = defaultdict(
            lambda: asyncio.Semaphore(self._per_domain_concurrency)
        )
        self._domain_last_request: dict[str, float] = defaultdict(float)
        self._lock = asyncio.Lock()

    def _compute_delay(self) -> float:
        """Calcula el delay con jitter aleatorio."""
        if self._delay_s <= 0 and self._jitter_s <= 0:
            return 0.0
        base = self._delay_s
        jitter = random.uniform(-self._jitter_s, self._jitter_s)
        return max(0.0, base + jitter)

    async def _wait_for_slot(self, domain: str) -> None:
        """Espera a que sea seguro enviar un request a este dominio."""
        # Adquirir semáforo del dominio
        await self._domain_sems[domain].acquire()

        # Aplicar delay temporal
        delay = self._compute_delay()
        if delay > 0:
            async with self._lock:
                now = time.monotonic()
                last = self._domain_last_request.get(domain, 0.0)
                elapsed = now - last
                wait = delay - elapsed
                if wait > 0:
                    await asyncio.sleep(wait)
                self._domain_last_request[domain] = time.monotonic()
        else:
            async with self._lock:
                self._domain_last_request[domain] = time.monotonic()

    def _release_slot(self, domain: str) -> None:
        """Libera el slot de concurrencia del dominio."""
        try:
            self._domain_sems[domain].release()
        except ValueError:
            pass  # Semáforo ya liberado (safety net)

    @asynccontextmanager
    async def throttle(self, url: str) -> AsyncIterator[None]:
        """Context manager para throttle por dominio.

        Uso:
            async with rate_limiter.throttle(url):
                resp = await client.get(url)
        """
        domain = extract_domain(url)
        await self._wait_for_slot(domain)
        try:
            yield
        finally:
            self._release_slot(domain)

    @property
    def retry_max_attempts(self) -> int:
        return self._retry_max

    @staticmethod
    def should_retry(status_code: int) -> bool:
        """Determina si el status code amerita un retry."""
        return status_code in (429, 503)

    @staticmethod
    def backoff_delay(attempt: int, retry_after: float | None = None) -> float:
        """Calcula el delay de backoff exponencial.

        Si hay un Retry-After válido, lo usa como base.
        Si no, usa backoff exponencial: 1s, 2s, 4s, 8s...
        """
        if retry_after is not None and retry_after > 0:
            # Añadir un pequeño jitter al Retry-After
            return retry_after + random.uniform(0.1, 0.5)
        # Backoff exponencial: 2^attempt seconds (1, 2, 4, 8...)
        base = min(2 ** attempt, 30)  # Cap en 30s
        return base + random.uniform(0.1, 0.5)


# ---------------------------------------------------------------------------
# Helper: request con retry integrado
# ---------------------------------------------------------------------------

async def request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    rate_limiter: DomainRateLimiter,
    *,
    headers: dict[str, str] | None = None,
    content: str | None = None,
) -> httpx.Response:
    """Ejecuta un HTTP request con rate limiting y retry en 429/503.

    Flujo:
    1. Adquiere slot del dominio (throttle).
    2. Envía request.
    3. Si 429/503 → espera backoff → reintenta (hasta retry_max_attempts).
    4. Retorna la respuesta (sea exitosa o el último retry).
    """
    last_response: httpx.Response | None = None

    for attempt in range(rate_limiter.retry_max_attempts + 1):
        async with rate_limiter.throttle(url):
            if method.upper() == "HEAD":
                resp = await client.head(url, headers=headers)
            elif method.upper() == "POST":
                resp = await client.post(url, content=content, headers=headers)
            else:
                resp = await client.get(url, headers=headers)

        last_response = resp

        if not rate_limiter.should_retry(resp.status_code):
            return resp

        # Es 429 o 503 → calcular backoff
        if attempt < rate_limiter.retry_max_attempts:
            retry_after = parse_retry_after(
                resp.headers.get("Retry-After") or resp.headers.get("retry-after")
            )
            delay = rate_limiter.backoff_delay(attempt, retry_after)
            await asyncio.sleep(delay)

    # Todos los reintentos agotados: devolver la última respuesta
    assert last_response is not None
    return last_response
