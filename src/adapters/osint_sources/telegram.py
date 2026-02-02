"""Scanner OSINT: Telegram.

Implementación mínima:
- Verifica existencia del username público vía `t.me/<username>`.

Nota:
- Telegram puede devolver contenido genérico para algunos casos. Por ahora
  mantenemos heurística simple basada en status code.
"""

from __future__ import annotations

from typing import Any

from adapters.http_client import build_async_client
from core.config import AppSettings
from core.domain.models import SocialProfile
from core.interfaces.scanner import OSINTScanner


class TelegramScanner(OSINTScanner):
    _base_url = "https://t.me"

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
                pattern_exist = r'<meta property="og:title" content="(.*?)"'
                ne = re.search(pattern_exist, html, re.IGNORECASE | re.DOTALL)
                nd=ne.group(1)
                if not nd.startswith("Telegram: Contact @"):
                    exists = True
                    
                    pattern_name = r'<meta name="title" content="(.*?)"'
                    nn = re.search(pattern_name, html, re.IGNORECASE | re.DOTALL)
                    if nn is not None:
                        name = nn.group(1)
                        metadata["name"] = name
                    
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
            network_name="telegram",
            existe=exists,
            metadata=metadata,
        )
