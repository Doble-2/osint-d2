"""Runner data-driven para listas de sitios (username/email).

Diseño:
- Ejecuta checks concurrentes con un semáforo global + rate limiting por dominio.
- Retry con backoff exponencial en 429/503.
- Devuelve solo hallazgos (FOUND) como `SocialProfile` para evitar inflar el output.

Limitaciones (MVP):
- Heurística simple basada en status code + strings en HTML.
- Headers y data se soportan en email-sites.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from adapters.http_client import build_async_client
from adapters.http_client import extract_html_metadata
from adapters.rate_limiter import (
    DomainRateLimiter,
    request_with_retry,
)
from adapters.site_lists.models import EmailSite, UsernameSite
from adapters.site_lists.operations import apply_input_operation
from core.config import AppSettings
from core.domain.models import SocialProfile

logger = logging.getLogger(__name__)


def _slug(name: str) -> str:
    out = []
    for ch in name.strip().lower():
        if ch.isalnum():
            out.append(ch)
        elif ch in ("-", "_"):
            out.append(ch)
        else:
            out.append("-")
    s = "".join(out).strip("-")
    return (s[:60] or "site")


def _is_nsfw(category: str | None) -> bool:
    if not category:
        return False
    return "nsfw" in category.lower()


def _match_found(*, text: str, status_code: int, e_code: int, e_string: str, m_code: int | None, m_string: str | None) -> bool:
    if status_code != e_code:
        return False
    if e_string not in text:
        return False
    if m_code is not None and status_code == m_code:
        return False
    if m_string and m_string in text:
        return False
    return True


async def run_username_sites(
    *,
    usernames: list[str],
    sites: list[UsernameSite],
    settings: AppSettings,
    max_concurrency: int,
    categories: set[str] | None,
    no_nsfw: bool,
) -> tuple[list[SocialProfile], int]:
    """Run username site checks. Returns (found_profiles, error_count)."""
    semaphore = asyncio.Semaphore(max(1, max_concurrency))

    # Rate limiter por dominio
    rate_limiter = DomainRateLimiter(
        per_domain_concurrency=settings.per_domain_concurrency,
        delay_ms=settings.request_delay_ms,
        jitter_ms=settings.request_jitter_ms,
        retry_max_attempts=settings.retry_max_attempts,
    )

    filtered: list[UsernameSite] = []
    for s in sites:
        if no_nsfw and _is_nsfw(s.cat):
            continue
        if categories and s.cat and s.cat.lower() not in categories:
            continue
        filtered.append(s)

    async with build_async_client(settings) as client:

        async def check(site: UsernameSite, username: str) -> SocialProfile | None:
            url = site.uri_check.replace("{account}", username)
            async with semaphore:
                try:
                    resp = await request_with_retry(
                        client, "GET", url, rate_limiter,
                    )
                    text = resp.text or ""

                    found = _match_found(
                        text=text,
                        status_code=resp.status_code,
                        e_code=site.e_code,
                        e_string=site.e_string,
                        m_code=site.m_code,
                        m_string=site.m_string,
                    )
                    if not found:
                        return None

                    html_meta = extract_html_metadata(html=text, base_url=str(resp.url))

                    metadata: dict[str, Any] = {
                        "status_code": resp.status_code,
                        "final_url": str(resp.url),
                        "category": site.cat,
                        "source": "site_list",
                        "site_name": site.name,
                        **html_meta,
                    }

                    return SocialProfile(
                        url=str(resp.url),
                        username=username,
                        network_name=_slug(site.name),
                        exists=True,
                        metadata=metadata,
                        bio=html_meta.get("meta_description"),
                        image_url=html_meta.get("og_image"),
                    )
                except Exception as exc:
                    logger.debug("Site-list check failed for %s on %s: %s", username, site.name, exc)
                    return exc

        results = await asyncio.gather(*(check(s, username) for s in filtered for username in usernames), return_exceptions=False)

    error_count = sum(1 for r in results if isinstance(r, Exception))
    found = [r for r in results if isinstance(r, SocialProfile)]
    if error_count:
        logger.info("Username site-list scan: %d found, %d errors.", len(found), error_count)
    return found, error_count


async def run_email_sites(
    *,
    emails: list[str],
    sites: list[EmailSite],
    settings: AppSettings,
    max_concurrency: int,
    categories: set[str] | None,
    no_nsfw: bool,
) -> tuple[list[SocialProfile], int]:
    """Run email site checks. Returns (found_profiles, error_count)."""
    semaphore = asyncio.Semaphore(max(1, max_concurrency))

    # Rate limiter por dominio
    rate_limiter = DomainRateLimiter(
        per_domain_concurrency=settings.per_domain_concurrency,
        delay_ms=settings.request_delay_ms,
        jitter_ms=settings.request_jitter_ms,
        retry_max_attempts=settings.retry_max_attempts,
    )

    filtered: list[EmailSite] = []
    for s in sites:
        if no_nsfw and _is_nsfw(s.cat):
            continue
        if categories and s.cat and s.cat.lower() not in categories:
            continue
        filtered.append(s)

    async with build_async_client(settings) as client:

        async def check(site: EmailSite, email: str) -> SocialProfile | None:
            processed = apply_input_operation(email, site.input_operation)
            url = site.uri_check.replace("{account}", processed)
            data = site.data.replace("{account}", processed) if site.data else None
            headers = site.headers
            method = (site.method or "GET").upper()

            async with semaphore:
                try:
                    resp = await request_with_retry(
                        client, method, url, rate_limiter,
                        headers=headers,
                        content=data,
                    )

                    text = resp.text or ""
                    found = _match_found(
                        text=text,
                        status_code=resp.status_code,
                        e_code=site.e_code,
                        e_string=site.e_string,
                        m_code=site.m_code,
                        m_string=site.m_string,
                    )
                    if not found:
                        return None

                    html_meta = extract_html_metadata(html=text, base_url=str(resp.url))

                    metadata: dict[str, Any] = {
                        "status_code": resp.status_code,
                        "final_url": str(resp.url),
                        "category": site.cat,
                        "source": "email_site_list",
                        "site_name": site.name,
                        "input_operation": site.input_operation,
                        **html_meta,
                    }

                    return SocialProfile(
                        url=str(resp.url),
                        username=email,
                        network_name=_slug(site.name),
                        exists=True,
                        metadata=metadata,
                        bio=html_meta.get("meta_description"),
                        image_url=html_meta.get("og_image"),
                    )
                except Exception as exc:
                    logger.debug("Email site-list check failed for %s on %s: %s", email, site.name, exc)
                    return exc

        results = await asyncio.gather(*(check(s, email) for s in filtered for email in emails), return_exceptions=False)

    error_count = sum(1 for r in results if isinstance(r, Exception))
    found = [r for r in results if isinstance(r, SocialProfile)]
    if error_count:
        logger.info("Email site-list scan: %d found, %d errors.", len(found), error_count)
    return found, error_count
