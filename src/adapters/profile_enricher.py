"""Enriquecimiento genérico de perfiles (HTML).

Se usa como fallback cuando:
- El scanner solo verificó existencia (200) pero no extrajo bio/avatar.
- Queremos aportar texto a IA sin depender de scrapers específicos.

Extrae (si existe):
- <title>
- meta[name=description]
- meta[property=og:image]
"""

from __future__ import annotations

import asyncio

from adapters.http_client import build_async_client, extract_html_metadata
from core.config import AppSettings
from core.domain.models import SocialProfile


async def enrich_profiles_from_html(
    *,
    profiles: list[SocialProfile],
    settings: AppSettings,
    max_concurrency: int = 20,
) -> None:
    sem = asyncio.Semaphore(max(1, max_concurrency))

    async with build_async_client(settings) as client:

        async def enrich_one(p: SocialProfile) -> None:
            if not p.existe:
                return
            # Si ya tenemos bio o imagen, no insistimos.
            if p.bio or p.imagen_url:
                return

            # Solo HTTP(S)
            url = str(p.url)
            if not (url.startswith("http://") or url.startswith("https://")):
                return

            async with sem:
                try:
                    resp = await client.get(url)
                    if resp.status_code < 200 or resp.status_code >= 400:
                        return

                    html = resp.text or ""
                    meta = extract_html_metadata(html=html, base_url=str(resp.url))
                    if not meta:
                        return

                    # Guarda todo en metadata para trazabilidad
                    if isinstance(p.metadata, dict):
                        p.metadata = {**p.metadata, **meta}

                    if not p.bio:
                        md = meta.get("meta_description")
                        if isinstance(md, str) and md.strip():
                            p.bio = md.strip()

                    if not p.imagen_url:
                        og = meta.get("og_image")
                        if isinstance(og, str) and og.strip():
                            p.imagen_url = og.strip()
                except Exception:
                    return

        await asyncio.gather(*(enrich_one(p) for p in profiles))
