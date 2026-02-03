"""Scanner OSINT: Pinterest.

Implementación mínima:
- Verifica existencia mediante HTTP status.

Nota:
- Pinterest puede aplicar anti-bot; este es un check best-effort.
"""

from __future__ import annotations

from typing import Any

from adapters.http_client import build_async_client
from core.config import AppSettings
from core.domain.models import SocialProfile
from core.interfaces.scanner import OSINTScanner
from bs4 import BeautifulSoup

class PinterestScanner(OSINTScanner):
    _base_url = "https://www.pinterest.com"

    def __init__(self, settings: AppSettings | None = None) -> None:
        self._settings = settings or AppSettings()

    async def scan(self, username: str) -> SocialProfile:
        import re
        url = f"{self._base_url}/{username}/"

        async with build_async_client(self._settings) as client:
            response = await client.get(url)

        exists = response.status_code == 200
        metadata: dict[str, Any] = {
            "status_code": response.status_code,
            "final_url": str(response.url),
        }
        soup = BeautifulSoup(response.text, "html.parser")
        
        if response.status_code == 200:
            # Extraer <title> del HTML
            html = response.text if hasattr(response, "text") else await response.aread()
            if not isinstance(html, str):
                html = html.decode(errors="ignore")
                
            #validamos existencia real del perfil con el div que contiene el nombre
            pattern_exist_div = r'<div class="H2DtUH KwViV7 FE_3R1 KDGhSV Tjcf3c sSBu24" data-test-id="profile-name"><div class="ADXRXN">(.*?)</div>'
            exist_soup = soup.find("div", {"data-test-id": "profile-name"})
            exist= exist_soup.find("div").text if exist_soup and exist_soup.find("div") else None
            #ne = re.search(pattern_exist_div, html, re.IGNORECASE | re.DOTALL)
            name= exist if exist is not None else None
            
            
            if name is not None:
                exists = True
                metadata["name"] = name
                
                pattern_desc = r'<span class="WuRgKB aMgNKE YfEt3H v_eFe4 qnEc35 hxKTA7 mm0O_j" data-test-id="main-user-description-text">(.*?)</span>'
                
                nd = re.search(pattern_desc, html, re.IGNORECASE | re.DOTALL)
                if nd is not None:
                    description = nd.group(1)
                    metadata["description"] = description 
                    
                pattern_avatar = fr'<img alt="{re.escape(name)}" class="iFOUS5" draggable="true" fetchpriority="auto" loading="auto" src="(.*?)"/>'
                na = re.search(pattern_avatar, html, re.IGNORECASE | re.DOTALL)
                if na is not None:
                    avatar_url = na.group(1)
                    metadata["avatar_url"] = avatar_url
                
                #pattern_website = r'<span class="WuRgKB eMU5i5 YfEt3H v_eFe4 qnEc35 hxKTA7 rszMzv">(.*?)</span>'
                website_section_soup= soup.find("div", {"data-test-id": "website-icon-and-url"})
                website= website_section_soup.find("span") if website_section_soup and website_section_soup.find("span") else None
                
                website_url= website.text if website and website.text else None
                
                #nw = re.search(pattern_website, html, re.IGNORECASE | re.DOTALL)
                

                if website_url is not None:
                    metadata["other_websites"] = website_url
        
            else:
                exists = False  
     

        return SocialProfile(
            url=str(response.url),
            username=username,
            network_name="pinterest",
            existe=exists,
            metadata=metadata,
        )
