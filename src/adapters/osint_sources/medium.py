"""Scanner OSINT: Medium.

Implementación mínima:
- Verifica existencia mediante HTTP status al perfil público.

Nota:
- Medium suele redirigir. Registramos la URL final y el status.
"""

from __future__ import annotations

from typing import Any

from adapters.http_client import build_async_client
from core.config import AppSettings
from core.domain.models import SocialProfile
from core.interfaces.scanner import OSINTScanner
from bs4 import BeautifulSoup


class MediumScanner(OSINTScanner):
    _base_url = "https://medium.com"

    def __init__(self, settings: AppSettings | None = None) -> None:
        self._settings = settings or AppSettings()

    async def scan(self, username: str) -> SocialProfile:
        url = f"{self._base_url}/@{username}"
        

        async with build_async_client(self._settings) as client:
            response = await client.get(url)
            metadata: dict[str, Any] = {
            "status_code": response.status_code,
            "final_url": str(response.url),
            }
            if response.status_code == 200:
                soup = BeautifulSoup(await response.aread(), "html.parser")
                
                html = response.text if hasattr(response, "text") else await response.aread()
                if not isinstance(html, str):
                    html = html.decode(errors="ignore")
                #"<meta data-rh="true" property="og:title" content="Chad Hamre – Medium" />"
                metatitle_soup = soup.find("meta", {"property": "og:title"})
                name = None
                if metatitle_soup and metatitle_soup.get("content"):
                    name = metatitle_soup.get("content")
                    

                
                if name is not None and name != "Medium":
                    exists = True
                    name= name.replace("– Medium", "").strip()
                    
                    
                    description_soup = soup.find("meta", {"name": "description"})
                    if description_soup and description_soup.get("content"):
                        description = description_soup.get("content")
                        metadata["description"] = description

                    avatar_soup = soup.find("meta", {"property": "og:image"})
                    if avatar_soup and avatar_soup.get("content"):
                        avatar_url = avatar_soup.get("content")
                        metadata["avatar_url"] = avatar_url
                    
                        
                    titles_soup = soup.find_all("h2")
                    titles = [t.get_text().strip() for t in titles_soup if t.get_text().strip()]
                    
                    contents_soup = soup.find_all("h3")
                    contents = [c.get_text().strip() for c in contents_soup if c.get_text().strip()]    
                    
                    posts=[]
                    
                    for t, c in zip(titles, contents):
                        posts.append({"title": t.strip(), "content": c.strip()})
                    if posts:
                        metadata["recent_posts"] = posts
                    
                else:
                    name = None
                    exists = False
                
                metadata["name"] = name
            else:
                exists = False
        
    
        return SocialProfile(
            url=str(response.url),
            username=username,
            network_name="medium",
            existe=exists,
            metadata=metadata,
        )
