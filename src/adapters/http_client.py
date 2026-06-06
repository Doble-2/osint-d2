"""Wrapper de httpx.

Por qué un wrapper:
- Estandariza timeouts, headers, retries, logging y políticas de proxy/Tor.
- Facilita testeo: se puede sustituir por un stub/mocked client.
- Centraliza la configuración de proxy (ScrapingAnt) en un solo punto.
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


# ---------------------------------------------------------------------------
# ScrapingAnt Proxy
# ---------------------------------------------------------------------------

_PROXY_ENDPOINTS: dict[str, str] = {
    "residential": "residential.scrapingant.com:8080",
    "datacenter": "datacenter.scrapingant.com:8080",
}

# Fallback for Web Scraping API Proxy Mode (when no username is provided).
_API_PROXY_ENDPOINT = "proxy.scrapingant.com:8080"


def _build_proxy_url(settings: AppSettings) -> str | None:
    """Build a ScrapingAnt proxy URL from settings.

    Supports two modes:

    1. **Standalone proxies** (when ``proxy_username`` is set):
       ``http://customer-USER-country-CC:KEY@residential.scrapingant.com:8080``
    2. **API Proxy Mode** (fallback, when only ``proxy_api_key`` is set):
       ``http://scrapingant&browser=false&proxy_type=MODE:KEY@proxy.scrapingant.com:8080``

    Returns an ``http://user:pass@host:port`` string suitable for
    ``httpx.AsyncClient(proxy=...)``, or ``None`` when proxy is disabled.
    """
    mode = settings.effective_proxy_mode
    if not mode or not settings.proxy_api_key:
        return None

    if mode not in ("residential", "datacenter"):
        return None

    password = settings.proxy_api_key

    if settings.proxy_username:
        # ── Standalone residential/datacenter proxy product ──
        # Format: customer-USERNAME[-country-CC][-sessionid-ID]
        username = f"customer-{settings.proxy_username}"
        if settings.proxy_country:
            username += f"-country-{settings.proxy_country}"
        endpoint = _PROXY_ENDPOINTS[mode]
    else:
        # ── API Proxy Mode (legacy / no username) ──
        username = f"scrapingant&browser=false&proxy_type={mode}"
        if settings.proxy_country:
            username += f"&proxy_country={settings.proxy_country}"
        endpoint = _API_PROXY_ENDPOINT

    return f"http://{username}:{password}@{endpoint}"


# ---------------------------------------------------------------------------
# Async HTTP Client Builder
# ---------------------------------------------------------------------------

def build_async_client(
    settings: AppSettings | None = None,
    *,
    extra_headers: dict[str, str] | None = None,
) -> httpx.AsyncClient:
    """Crea un ``httpx.AsyncClient`` con defaults seguros.

    Por qué un builder:
    - Centraliza timeouts/headers para que todas las fuentes se comporten igual.
    - Inyecta proxy ScrapingAnt de forma transparente si está configurado.
    """

    settings = settings or AppSettings()
    headers: dict[str, str] = {
        "User-Agent": settings.user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    if extra_headers:
        headers.update(extra_headers)

    proxy_url = _build_proxy_url(settings)

    return httpx.AsyncClient(
        timeout=httpx.Timeout(settings.http_timeout_seconds),
        follow_redirects=True,
        headers=headers,
        proxy=proxy_url,
        verify=proxy_url is None,  # Proxy handles TLS termination.
    )


# ---------------------------------------------------------------------------
# HTML Metadata Extraction
# ---------------------------------------------------------------------------

def extract_html_metadata(*, html: str, base_url: str | None = None) -> dict[str, Any]:
    """Extrae metadata ligera de HTML.

    Requisitos:
    - ``beautifulsoup4`` instalado.

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
