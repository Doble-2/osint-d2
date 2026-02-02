"""Scanner OSINT: Twitch.

Implementación mínima:
- Verifica existencia mediante HTTP status al canal público.
"""

from __future__ import annotations

from typing import Any

from adapters.http_client import build_async_client
from core.config import AppSettings
from core.domain.models import SocialProfile
from core.interfaces.scanner import OSINTScanner


class TwitchScanner(OSINTScanner):
    _base_url = "https://www.twitch.tv"

    def __init__(self, settings: AppSettings | None = None) -> None:
        self._settings = settings or AppSettings()

    async def scan(self, username: str) -> SocialProfile:
        import re
        url = f"{self._base_url}/{username}"

        async with build_async_client(self._settings) as client:
            response = await client.get(url)
        
        metadata: dict[str, Any] = {
            "status_code": response.status_code,
            "final_url": str(response.url),
        }
        
        if response.status_code == 200:
            # Extraer <title> del HTML
            html = response.text if hasattr(response, "text") else await response.aread()
            if not isinstance(html, str):
                html = html.decode(errors="ignore")
            patternExist = r'<meta property="og:title" content="(.*?)"'
            ne = re.search(patternExist, html, re.IGNORECASE | re.DOTALL)
            
            if ne is not None:
                exists = True
                
                pattern_desc = r'<meta name="description" content="(.*?)"'
                nd = re.search(pattern_desc, html, re.IGNORECASE | re.DOTALL)
                if nd is not None:
                    description = nd.group(1)
                    metadata["description"] = description
                
                pattern_avatar = r'<meta property="og:image" content="(.*?)"'
                na = re.search(pattern_avatar, html, re.IGNORECASE | re.DOTALL)
                if na is not None:
                    avatar_url = na.group(1)
                    metadata["avatar_url"] = avatar_url
        
            else:
                exists = False  
                
        return SocialProfile(
            url=str(response.url),
            username=username,
            network_name="twitch",
            existe=exists,
            metadata=metadata,
        )
