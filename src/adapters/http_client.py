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


def _build_proxy_url(
    settings: AppSettings,
) -> tuple[str, tuple[str, str]] | tuple[None, None]:
    """Build a ScrapingAnt proxy URL from settings.

    Supports two modes:

    1. **Standalone proxies** (when ``proxy_username`` is set):
       ``http://residential.scrapingant.com:8080`` + auth tuple
    2. **API Proxy Mode** (fallback, when only ``proxy_api_key`` is set):
       ``http://proxy.scrapingant.com:8080`` + auth tuple

    Returns ``(base_url, (username, password))`` — credentials are **never**
    embedded in the URL string — or ``(None, None)`` when proxy is disabled.
    """
    mode = settings.effective_proxy_mode
    if not mode or not settings.proxy_api_key:
        return None, None

    if mode not in ("residential", "datacenter"):
        return None, None

    password = settings.proxy_api_key.get_secret_value()

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

    return f"http://{endpoint}", (username, password)


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

    Security: proxy credentials are passed via ``httpx.Proxy(auth=...)``
    instead of being embedded in the URL, so they never leak into exception
    messages, debug logs, or tracebacks.
    """

    settings = settings or AppSettings()
    headers: dict[str, str] = {
        "User-Agent": settings.user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    if extra_headers:
        headers.update(extra_headers)

    proxy_base, proxy_auth = _build_proxy_url(settings)

    proxy = None
    if proxy_base and proxy_auth:
        proxy = httpx.Proxy(proxy_base, auth=proxy_auth)

    return httpx.AsyncClient(
        timeout=httpx.Timeout(settings.http_timeout_seconds),
        follow_redirects=True,
        headers=headers,
        proxy=proxy,
        verify=proxy is None,  # Proxy handles TLS termination.
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
    - emails           (list[str])
    - social_links     (list[dict] con {network, url, username})
    - external_links   (list[str])
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

    # ── Extract emails from full page text ──
    import re as _re  # noqa: E402 — lazy import to keep top-level light
    page_text = soup.get_text(" ", strip=True) + " "
    # Also scan href="mailto:..." links.
    for a in soup.find_all("a", href=True):
        href = str(a["href"])
        if href.startswith("mailto:"):
            page_text += " " + href.replace("mailto:", "") + " "
    email_pattern = _re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
    emails_found = sorted(set(email_pattern.findall(page_text)))

    # ── Extract social media links ──
    _SOCIAL_PATTERNS: dict[str, _re.Pattern[str]] = {
        "github": _re.compile(r"github\.com/([a-zA-Z0-9_\-]+)"),
        "gitlab": _re.compile(r"gitlab\.com/([a-zA-Z0-9_\-]+)"),
        "twitter": _re.compile(r"(?:twitter|x)\.com/([a-zA-Z0-9_]+)"),
        "linkedin": _re.compile(r"linkedin\.com/in/([a-zA-Z0-9_\-]+)"),
        "instagram": _re.compile(r"instagram\.com/([a-zA-Z0-9_.]+)"),
        "youtube": _re.compile(r"youtube\.com/(?:@|channel/|c/)([a-zA-Z0-9_\-]+)"),
        "tiktok": _re.compile(r"tiktok\.com/@([a-zA-Z0-9_.]+)"),
        "facebook": _re.compile(r"facebook\.com/([a-zA-Z0-9_.]+)"),
        "medium": _re.compile(r"medium\.com/@([a-zA-Z0-9_.\-]+)"),
        "dev.to": _re.compile(r"dev\.to/([a-zA-Z0-9_]+)"),
        "behance": _re.compile(r"behance\.net/([a-zA-Z0-9_\-]+)"),
        "dribbble": _re.compile(r"dribbble\.com/([a-zA-Z0-9_\-]+)"),
        "soundcloud": _re.compile(r"soundcloud\.com/([a-zA-Z0-9_\-]+)"),
        "twitch": _re.compile(r"twitch\.tv/([a-zA-Z0-9_]+)"),
        "telegram": _re.compile(r"t\.me/([a-zA-Z0-9_]+)"),
        "reddit": _re.compile(r"reddit\.com/(?:u|user)/([a-zA-Z0-9_\-]+)"),
        "keybase": _re.compile(r"keybase\.io/([a-zA-Z0-9_]+)"),
        "mastodon": _re.compile(r"(@[a-zA-Z0-9_]+@[a-zA-Z0-9.\-]+)"),
    }

    social_links: list[dict[str, str]] = []
    seen_socials: set[tuple[str, str]] = set()

    all_links = [str(a.get("href", "")) for a in soup.find_all("a", href=True)]
    full_html = html  # also scan raw HTML for social references

    for network, pattern in _SOCIAL_PATTERNS.items():
        for source in all_links + [full_html]:
            for match in pattern.finditer(source):
                username = match.group(1)
                if (network, username.lower()) in seen_socials:
                    continue
                seen_socials.add((network, username.lower()))
                # Reconstruct URL from match.
                url_match = match.group(0)
                if not url_match.startswith("http"):
                    url_match = f"https://{url_match}"
                social_links.append({
                    "network": network,
                    "url": url_match,
                    "username": username,
                })

    # ── Collect external links (up to 20) ──
    external_links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = str(a["href"])
        if href.startswith("http") and len(external_links) < 20:
            external_links.append(href)

    out: dict[str, Any] = {}
    if title:
        out["title"] = title
    if meta_description:
        out["meta_description"] = meta_description
    if og_image:
        out["og_image"] = og_image
    if emails_found:
        out["emails"] = emails_found
    if social_links:
        out["social_links"] = social_links
    if external_links:
        out["external_links"] = external_links
    return out

