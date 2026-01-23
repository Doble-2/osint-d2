"""Runner para el manifest de Sherlock (400+ sitios).

- Descarga/carga del manifest: `core.resources_loader.load_sherlock_data()`.
- Este runner ejecuta checks concurrentes y devuelve SOLO hallazgos (FOUND).

Soporta un subset práctico de `errorType`:
- status_code
- message
- response_url

Nota: el manifest real tiene muchos detalles; este es un MVP conservador.
"""

from __future__ import annotations

import asyncio
from typing import Any
from collections.abc import Callable

from adapters.http_client import build_async_client, extract_html_metadata
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


def _is_nsfw(info: dict[str, Any]) -> bool:
    v = info.get("isNSFW")
    return bool(v)


def _interpolate(url_template: str, username: str) -> str:
    if "{}" in url_template:
        return url_template.replace("{}", username)
    try:
        return url_template.format(username)
    except Exception:
        return url_template


def _contains_any(text: str, needle: Any) -> bool:
    if not needle:
        return False
    if isinstance(needle, str):
        return needle in text
    if isinstance(needle, list):
        return any(isinstance(n, str) and n in text for n in needle)
    return False


async def run_sherlock_username(
    *,
    username: str,
    manifest: dict[str, Any],
    settings: AppSettings,
    max_concurrency: int,
    no_nsfw: bool,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> list[SocialProfile]:
    sem = asyncio.Semaphore(max(1, max_concurrency))

    # Manifest es dict: site_name -> info
    items: list[tuple[str, dict[str, Any]]] = []
    for site_name, info in manifest.items():
        if site_name == "$schema":
            continue
        if not isinstance(info, dict):
            continue
        if no_nsfw and _is_nsfw(info):
            continue
        items.append((site_name, info))

    total = len(items)
    if progress_callback:
        # Primer tick: permite inicializar la UI.
        progress_callback(0, total, "")

    async with build_async_client(settings) as client:

        async def check(site_name: str, info: dict[str, Any]) -> SocialProfile | None:
            url_t = info.get("url")
            if not isinstance(url_t, str) or not url_t:
                return None

            url = _interpolate(url_t, username)
            error_type = info.get("errorType")
            if isinstance(error_type, str):
                error_types = [error_type]
            elif isinstance(error_type, list):
                error_types = [t for t in error_type if isinstance(t, str)]
            else:
                error_types = []

            headers = info.get("headers") if isinstance(info.get("headers"), dict) else None
            request_method = info.get("request_method")
            if not isinstance(request_method, str):
                request_method = "GET"
            request_method = request_method.upper()

            async with sem:
                try:
                    if request_method == "HEAD":
                        resp = await client.head(url, headers=headers)
                        text = ""
                    else:
                        resp = await client.get(url, headers=headers)
                        text = resp.text or ""

                    status = resp.status_code
                    final_url = str(resp.url)

                    exists = None

                    if "response_url" in error_types:
                        exists = 200 <= status < 300

                    if "status_code" in error_types and exists is None:
                        error_codes = info.get("errorCode")
                        if isinstance(error_codes, int):
                            error_codes = [error_codes]
                        if isinstance(error_codes, list):
                            error_codes = [c for c in error_codes if isinstance(c, int)]
                        else:
                            error_codes = None

                        if status < 200 or status >= 300:
                            exists = False
                        elif error_codes and status in error_codes:
                            exists = False
                        else:
                            exists = True

                    if "message" in error_types and exists is None:
                        error_msg = info.get("errorMsg")
                        # Si el errorMsg aparece, entonces NO existe.
                        exists = not _contains_any(text, error_msg)

                    if exists is None:
                        # Fallback conservador
                        exists = 200 <= status < 300

                    if not exists:
                        return None

                    html_meta = extract_html_metadata(html=text, base_url=final_url)
                    metadata: dict[str, Any] = {
                        "source": "sherlock",
                        "site_name": site_name,
                        "url_main": info.get("urlMain"),
                        "errorType": error_types,
                        "status_code": status,
                        "final_url": final_url,
                        **html_meta,
                    }

                    return SocialProfile(
                        url=final_url,
                        username=username,
                        network_name=_slug(site_name),
                        existe=True,
                        metadata=metadata,
                        bio=html_meta.get("meta_description"),
                        imagen_url=html_meta.get("og_image"),
                    )
                except Exception:
                    return None

        tasks: list[asyncio.Task[SocialProfile | None]] = []
        for name, info in items:
            t = asyncio.create_task(check(name, info), name=name)
            tasks.append(t)

        completed = 0
        found: list[SocialProfile] = []
        for t in asyncio.as_completed(tasks):
            r = await t
            completed += 1
            if progress_callback:
                try:
                    progress_callback(completed, total, t.get_name())
                except Exception:
                    # Nunca dejar que la UI rompa el scanning.
                    pass
            if r is not None:
                found.append(r)

    return found
