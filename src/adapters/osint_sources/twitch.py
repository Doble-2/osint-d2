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
from bs4 import BeautifulSoup

class TwitchScanner(OSINTScanner):
    _base_url = "https://www.twitch.tv"

    def __init__(self, settings: AppSettings | None = None) -> None:
        self._settings = settings or AppSettings()

    async def scan(self, username: str) -> SocialProfile:
        #import re
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
            soup = BeautifulSoup(html, "html.parser")
            title_soup = soup.find("meta", {"property": "og:title"})
            
            name = None
            if title_soup:
                name = title_soup.get("content", "").replace("Twitch", "").strip(" ·-")
                metadata["name"] = name
            if title_soup is not None:
                exists = True
                
                #pattern_desc = r'<meta name="description" content="(.*?)"'
                desc_soup = soup.find("meta", {"name": "description"})
                
                if desc_soup is not None:
                    description = desc_soup.get("content")
                    metadata["description"] = description
                
                #pattern_avatar = r'<meta property="og:image" content="(.*?)"'
                avatar_soup = soup.find("meta", {"property": "og:image"})
                if avatar_soup is not None:
                    avatar_url = avatar_soup.get("content")
                    metadata["avatar_url"] = avatar_url
                #na = re.search(pattern_avatar, html, re.IGNORECASE | re.DOTALL)
        
            else:
                exists = False  
                                
        return SocialProfile(
            url=str(response.url),
            username=username,
            network_name="twitch",
            existe=exists,
            metadata=metadata,
        )
