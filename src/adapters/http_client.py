"""Wrapper de httpx.

Por qué un wrapper:
- Estandariza timeouts, headers, retries, logging y políticas de proxy/Tor.
- Facilita testeo: se puede sustituir por un stub/mocked client.

Nota: implementación pendiente (solo andamiaje).
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

import httpx

from core.config import AppSettings

try:
    from bs4 import BeautifulSoup
except Exception:  # pragma: no cover
    BeautifulSoup = None  # type: ignore


def build_async_client(
    settings: AppSettings | None = None,
    *,
    extra_headers: dict[str, str] | None = None,
) -> httpx.AsyncClient:
    """Crea un `httpx.AsyncClient` con defaults seguros.

    Por qué un builder:
    - Centraliza timeouts/headers para que todas las fuentes se comporten igual.
    - Facilita testeo y futuras políticas (retries, proxies, Tor).
    """

    settings = settings or AppSettings()
    headers: dict[str, str] = {
        "User-Agent": settings.user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    if extra_headers:
        headers.update(extra_headers)
    return httpx.AsyncClient(
        timeout=httpx.Timeout(settings.http_timeout_seconds),
        follow_redirects=True,
        headers=headers,
    )


def extract_html_metadata(*, html: str, base_url: str | None = None) -> dict[str, Any]:
    """Extrae metadata ligera de HTML.

    Requisitos:
    - `beautifulsoup4` instalado.

    Devuelve keys opcionales:
    - title
    - meta_description
    - og_image
    """

    if not html:
        return {}
    if BeautifulSoup is None:
        return {}

    soup = BeautifulSoup(html, "html.parser")

    title = None
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    meta_description = None
    tag = soup.find("meta", attrs={"name": "description"})
    if tag and tag.get("content"):
        meta_description = str(tag.get("content")).strip()

    og_image = None
    og = soup.find("meta", attrs={"property": "og:image"})
    if og and og.get("content"):
        og_image = str(og.get("content")).strip()
        if base_url:
            og_image = urljoin(base_url, og_image)

    out: dict[str, Any] = {}
    if title:
        out["title"] = title
    if meta_description:
        out["meta_description"] = meta_description
    if og_image:
        out["og_image"] = og_image
    return out
