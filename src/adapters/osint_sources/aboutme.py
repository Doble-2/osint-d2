"""Scanner OSINT: about.me.

Implementación mínima:
- Verifica existencia mediante HTTP status al perfil público.
"""

from __future__ import annotations

from typing import Any

from adapters.http_client import build_async_client
from core.config import AppSettings
from core.domain.models import SocialProfile
from core.interfaces.scanner import OSINTScanner
from bs4 import BeautifulSoup

#todo: extraccion de js (evaluar selecto lax? xpath?)
class AboutMeScanner(OSINTScanner):
    _base_url = "https://about.me"

    def __init__(self, settings: AppSettings | None = None) -> None:
        self._settings = settings or AppSettings()

    async def scan(self, username: str) -> SocialProfile | list[SocialProfile]:
        import re
        url = f"{self._base_url}/{username}"

        async with build_async_client(self._settings) as client:
            response = await client.get(url)
            metadata: dict[str, Any] = {
                "status_code": response.status_code,
                "final_url": str(response.url),
            }
            exists = response.status_code == 200
        
            if exists:
                html = response.text if hasattr(response, "text") else await response.aread()
                if not isinstance(html, str):
                    html = html.decode(errors="ignore")
                
                soup = BeautifulSoup(html, "html.parser")
                #validamos existencia real del perfil con el div que contiene el nombre
                #pattern_exist_div = r'<title>(.*?)</title>'
                title_soup = soup.find("title")
                #ne = re.search(pattern_exist_div, html, re.IGNORECASE | re.DOTALL)
                title= title_soup.text if title_soup is not None else None
                
                if title is not None:
                    who = title.replace("| about.me", "").strip(" ·-")
                    #metadata["name"] = who
                    # who = username userlastname - New Orleans, Louisiana
                    name= who.split(" - ")[0].strip()
                    metadata["name"]= name
                    
                    bio_soup = soup.find("meta", {"property": "og:description"})
                    bio= bio_soup.get("content") if bio_soup and bio_soup.get("content") else None
                    #pattern_bio = r'"bio":"(.*?)",'
                    #nb = re.search(pattern_bio, html, re.IGNORECASE | re.DOTALL)
                    #bio= nb.group(1) if nb is not None else None
                    metadata["bio"] = bio
                    
                    description_section_soup = soup.find("section", {"class": "bio"})
                    if description_section_soup != None:
                        description= description_section_soup.find("p").text if description_section_soup and description_section_soup.find("p") else None
                    #pattern_desc = r'"description":"(.*?)",'
                    #nd = re.search(pattern_desc, html, re.IGNORECASE | re.DOTALL)
                    #description= nd.group(1) if nd is not None else None
                    metadata["description"] = description 
                    
                    #pattern_avatar = r'"image":{"url":"(.*?)",'
                    
                    avatar_soup = soup.find("meta", {"property": "og:image"})
                    avatar= avatar_soup.get("content") if avatar_soup and avatar_soup.get("content") else None
                    #na = re.search(pattern_avatar, html, re.IGNORECASE | re.DOTALL)
                    if avatar is not None:
                        metadata["avatar_url"] = avatar
            
                    
                    pattern_location = r'"address":"(.*?)",' 
                    nl = re.search(pattern_location, html, re.IGNORECASE | re.DOTALL)
                    location= nl.group(1) if nl is not None else None
                    if location is None:
                        location= who.split(" - ")[1].strip() if len(who.split(" - "))>1 else None
                    metadata["location"] = location
                    
                    pattern_job=r'"jobTitle":"(.*?)",'
                    nj= re.search(pattern_job, html, re.IGNORECASE | re.DOTALL)
                    job= nj.group(1) if nj is not None else None
                    metadata["jobTitle"] = job
                    
                    pattern_interests = r'"knowsAbout":\s*\[(.*?)\]'
                    ni = re.search(pattern_interests, html, re.IGNORECASE | re.DOTALL)
                    if ni:
                        # Extrae todos los elementos entre comillas
                        interests = re.findall(r'"(.*?)"', ni.group(1))
                    else:
                        interests = None
                    metadata["interests"] = interests
                    
                    pattern_socials = r'"sameAs":\s*\[(.*?)\]'
                    ns = re.search(pattern_socials, html, re.IGNORECASE | re.DOTALL)
                    
                    social_links = []
                    if ns:
                        # Extrae todos los elementos entre comillas
                        social_links = re.findall(r'"(.*?)"', ns.group(1))
                        
                    metadata["social_links"] = social_links
                    

                    
                
                
                if name is not None:
                    exists = True
                    metadata["name"] = name
                        

            main_profile= SocialProfile(
                url=str(response.url),
                username=username,
                network_name="aboutme",
                existe=exists,
                metadata=metadata,
            )
            
            # Creamos perfiles adicionales para que aparezcan en la tabla
            extra_profiles = []
            
            if "social_links" in metadata:
                for link in metadata["social_links"]:
                    extra_profiles.append(SocialProfile(
                        url=link,
                        username=link.split("/")[-1],
                        network_name="aboutme_social_link",
                        existe=True,
                        metadata={"source": "aboutme", "from_username": username},
                    ))
                    

        # Retornamos todos los perfiles (el principal y los extras)
        if extra_profiles:
            return [main_profile] + extra_profiles
        return main_profile

