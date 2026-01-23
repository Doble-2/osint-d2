"""Runner data-driven para listas de sitios (username/email).

Diseño:
- Ejecuta checks concurrentes con un semáforo.
- Devuelve solo hallazgos (FOUND) como `SocialProfile` para evitar inflar el output.

Limitaciones (MVP):
- Heurística simple basada en status code + strings en HTML.
- Headers y data se soportan en email-sites.
"""

from __future__ import annotations

import asyncio
from typing import Any

from adapters.http_client import build_async_client
from adapters.http_client import extract_html_metadata
from adapters.site_lists.models import EmailSite, UsernameSite
from adapters.site_lists.operations import apply_input_operation
from core.config import AppSettings
from core.domain.models import SocialProfile


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
    username: str,
    sites: list[UsernameSite],
    settings: AppSettings,
    max_concurrency: int,
    categories: set[str] | None,
    no_nsfw: bool,
) -> list[SocialProfile]:
    semaphore = asyncio.Semaphore(max(1, max_concurrency))

    filtered: list[UsernameSite] = []
    for s in sites:
        if no_nsfw and _is_nsfw(s.cat):
            continue
        if categories and s.cat and s.cat.lower() not in categories:
            continue
        filtered.append(s)

    async with build_async_client(settings) as client:

        async def check(site: UsernameSite) -> SocialProfile | None:
            url = site.uri_check.replace("{account}", username)
            async with semaphore:
                try:
                    resp = await client.get(url)
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
                        existe=True,
                        metadata=metadata,
                        bio=html_meta.get("meta_description"),
                        imagen_url=html_meta.get("og_image"),
                    )
                except Exception as exc:
                    # Errores: para masivo preferimos no contaminar con cientos de errores.
                    return None

        results = await asyncio.gather(*(check(s) for s in filtered), return_exceptions=False)

    return [r for r in results if r is not None]


async def run_email_sites(
    *,
    email: str,
    sites: list[EmailSite],
    settings: AppSettings,
    max_concurrency: int,
    categories: set[str] | None,
    no_nsfw: bool,
) -> list[SocialProfile]:
    semaphore = asyncio.Semaphore(max(1, max_concurrency))

    filtered: list[EmailSite] = []
    for s in sites:
        if no_nsfw and _is_nsfw(s.cat):
            continue
        if categories and s.cat and s.cat.lower() not in categories:
            continue
        filtered.append(s)

    async with build_async_client(settings) as client:

        async def check(site: EmailSite) -> SocialProfile | None:
            processed = apply_input_operation(email, site.input_operation)
            url = site.uri_check.replace("{account}", processed)
            data = site.data.replace("{account}", processed) if site.data else None
            headers = site.headers
            method = (site.method or "GET").upper()

            async with semaphore:
                try:
                    if method == "POST":
                        resp = await client.post(url, content=data, headers=headers)
                    else:
                        resp = await client.get(url, headers=headers)

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
                        existe=True,
                        metadata=metadata,
                        bio=html_meta.get("meta_description"),
                        imagen_url=html_meta.get("og_image"),
                    )
                except Exception:
                    return None

        results = await asyncio.gather(*(check(s) for s in filtered), return_exceptions=False)

    return [r for r in results if r is not None]
