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
from bs4 import BeautifulSoup

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
                soup = BeautifulSoup(html, "html.parser")
                #pattern_exist = r'<meta property="og:title" content="(.*?)"'
                #ne = re.search(pattern_exist, html, re.IGNORECASE | re.DOTALL)
                #nd=ne.group(1)
                title_soup = soup.find("meta", {"property": "og:title"})
                title_content = title_soup.get("content") if title_soup else ""
                if not title_content.startswith("Telegram: Contact @"):
                    exists = True
                    name_section_soup = soup.find("div", {"class": "tgme_page_title"})
                    #name = <div class="tgme_page_title"><span dir="auto">Chad Fowler</span></div>
                    #name_section= name_section_soup.get("content")
                    name = None
                    if name_section_soup:
                        name_span = name_section_soup.find("span")
                        if name_span:
                            name = name_span.text
                    if name:
                        metadata["name"] = name
                    #print(name)

                    #pattern_name = r'<meta name="title" content="(.*?)"'
                    #nn = re.search(pattern_name, html, re.IGNORECASE | re.DOTALL)
                    #name = nn.group(1)
                    
                    avatar_soup = soup.find("meta", {"property": "og:image"})
                    #pattern_avatar = r'<meta property="og:image" content="(.*?)"'
                    #na = re.search(pattern_avatar, html, re.IGNORECASE | re.DOTALL)
                    if avatar_soup is not None:
                        avatar_url = avatar_soup.get("content")
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
