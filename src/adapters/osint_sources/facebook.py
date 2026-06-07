"""Scanner OSINT: Facebook.

URL:
- `https://www.facebook.com/<username>`

Extraction strategy (no auth required):
- Fetches the public profile/page URL via proxy.
- Parses `<meta>` OG tags for: display name, avatar, description.
- Detects login redirects (Facebook blocks non-authenticated requests
  aggressively).
- Distinguishes between profiles, pages, and non-existent usernames.

Limitations:
- Facebook is the most aggressive anti-scraping platform. A residential
  proxy is **strongly** recommended.
- Most profile content is hidden behind login walls. We can only
  extract publicly visible OG metadata.
- Pages (business/creator) tend to expose more data than personal profiles.
"""

from __future__ import annotations

import re
from typing import Any

from adapters.http_client import build_async_client
from core.config import AppSettings
from core.domain.models import SocialProfile
from core.interfaces.scanner import OSINTScanner


def _extract_og(html_str: str, prop: str) -> str | None:
    """Extract content from an Open Graph meta tag."""
    import html as html_mod

    # property="..." content="..."
    m = re.search(
        rf'<meta[^>]*property="{re.escape(prop)}"[^>]*content="([^"]*)"',
        html_str, re.IGNORECASE,
    )
    if m:
        return html_mod.unescape(m.group(1).strip())
    # reversed attribute order
    m2 = re.search(
        rf'<meta[^>]*content="([^"]*)"[^>]*property="{re.escape(prop)}"',
        html_str, re.IGNORECASE,
    )
    if m2:
        return html_mod.unescape(m2.group(1).strip())
    return None


def _extract_title(html: str) -> str | None:
    """Extract <title> content."""
    m = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
    return m.group(1).strip() if m else None


def _parse_likes(html: str) -> str | None:
    """Try to extract like/follower count from page HTML."""
    # Facebook pages sometimes include this in og:description or the HTML.
    # Pattern: "4,041 likes" or "1.2K likes"
    m = re.search(r'([\d,.]+[KMkm]?)\s+(?:likes?|followers?)', html, re.IGNORECASE)
    return m.group(1) if m else None


class FacebookScanner(OSINTScanner):
    _base_url = "https://www.facebook.com"

    def __init__(self, settings: AppSettings | None = None) -> None:
        self._settings = settings or AppSettings()

    async def scan(self, username: str) -> SocialProfile:
        url = f"{self._base_url}/{username}"

        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
        }

        async with build_async_client(self._settings, extra_headers=headers) as client:
            response = await client.get(url, follow_redirects=True)

        html = response.text or ""
        final_url = str(response.url)
        status = response.status_code

        metadata: dict[str, Any] = {
            "status_code": status,
            "final_url": final_url,
        }

        bio: str | None = None
        image_url: str | None = None
        exists = False

        # Facebook redirects to login for most requests.
        is_login_redirect = "/login" in final_url or "/checkpoint" in final_url
        # Generic "page not found" or profile doesn't exist.
        is_not_found = status == 404

        if is_login_redirect:
            metadata["blocked"] = True
            metadata["note"] = (
                "Facebook redirected to login — residential proxy recommended."
            )
        elif not is_not_found and status == 200 and html:
            # ── Extract OG metadata ──
            og_title = _extract_og(html, "og:title")
            og_desc = _extract_og(html, "og:description")
            og_image = _extract_og(html, "og:image")
            og_type = _extract_og(html, "og:type")
            page_title = _extract_title(html)

            # Heuristic: if og:title exists and isn't a generic FB page,
            # the profile/page exists.
            generic_titles = {
                "facebook", "facebook - log in or sign up",
                "facebook – log in or sign up",
                "log in to facebook", "page not found",
            }

            title_to_check = (og_title or page_title or "").lower().strip()

            if title_to_check and title_to_check not in generic_titles:
                exists = True

                if og_title:
                    metadata["name"] = og_title
                if og_desc:
                    bio = og_desc
                    metadata["description"] = og_desc
                if og_image:
                    image_url = og_image
                if og_type:
                    metadata["type"] = og_type  # "profile" or "page"
                if page_title:
                    metadata["title"] = page_title

                # Try to get like/follower counts.
                likes = _parse_likes(html)
                if likes:
                    metadata["likes"] = likes

                # Detect page vs profile.
                if og_type and "profile" in og_type.lower():
                    metadata["account_type"] = "profile"
                elif og_type and "page" in og_type.lower():
                    metadata["account_type"] = "page"
                elif "likes" in metadata:
                    metadata["account_type"] = "page"

        return SocialProfile(
            url=f"{self._base_url}/{username}",
            username=username,
            network_name="facebook",
            exists=exists,
            metadata=metadata,
            bio=bio,
            image_url=image_url,
        )
