"""Scanner OSINT: Instagram.

URL:
- `https://www.instagram.com/<username>/`

Extraction strategy (no auth required):
- Fetches the public profile page via residential proxy.
- Parses `<meta>` OG tags for: display name, bio, avatar, follower counts.
- Attempts to parse `<script type="application/ld+json">` for structured data.
- Falls back to `<meta>` tag scraping when JSON-LD is unavailable.

Note:
- Instagram aggressively blocks bots. A residential proxy is highly
  recommended for reliable results.
- This scanner only accesses **public** profile information.
"""

from __future__ import annotations

import json
import re
from typing import Any

from adapters.http_client import build_async_client
from core.config import AppSettings
from core.domain.models import SocialProfile
from core.interfaces.scanner import OSINTScanner


def _extract_og_content(html_str: str, property_name: str) -> str | None:
    """Extract content from an Open Graph meta tag.

    Returns the unescaped value (``&amp;`` → ``&``, etc.).
    """
    import html as html_mod

    # Match both property="..." and content="..." in either order.
    pattern = re.compile(
        rf'<meta[^>]*property="{re.escape(property_name)}"[^>]*content="([^"]*)"',
        re.IGNORECASE,
    )
    match = pattern.search(html_str)
    if match:
        return html_mod.unescape(match.group(1).strip())
    # Try reversed attribute order.
    pattern2 = re.compile(
        rf'<meta[^>]*content="([^"]*)"[^>]*property="{re.escape(property_name)}"',
        re.IGNORECASE,
    )
    match2 = pattern2.search(html_str)
    if match2:
        return html_mod.unescape(match2.group(1).strip())
    return None


def _parse_follower_counts(description: str | None) -> dict[str, Any]:
    """Parse follower/following/post counts from og:description.

    Instagram's og:description typically looks like:
    "1,234 Followers, 567 Following, 89 Posts - See Instagram photos and videos from Name (@handle)"
    """
    if not description:
        return {}

    out: dict[str, Any] = {}

    followers_match = re.search(r"([\d,.]+[KMkm]?)\s+Followers", description, re.IGNORECASE)
    if followers_match:
        out["followers"] = followers_match.group(1).replace(",", "")

    following_match = re.search(r"([\d,.]+[KMkm]?)\s+Following", description, re.IGNORECASE)
    if following_match:
        out["following"] = following_match.group(1).replace(",", "")

    posts_match = re.search(r"([\d,.]+[KMkm]?)\s+Posts", description, re.IGNORECASE)
    if posts_match:
        out["posts"] = posts_match.group(1).replace(",", "")

    # Extract display name from "... from Name (@handle)"
    name_match = re.search(r"from\s+(.+?)\s*\(@", description)
    if name_match:
        out["display_name"] = name_match.group(1).strip()

    return out


def _parse_json_ld(html: str) -> dict[str, Any]:
    """Try to extract structured data from JSON-LD script tags."""
    pattern = re.compile(
        r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
        re.DOTALL | re.IGNORECASE,
    )
    for match in pattern.finditer(html):
        try:
            data = json.loads(match.group(1))
            if isinstance(data, dict) and data.get("@type") == "ProfilePage":
                return data
        except (json.JSONDecodeError, TypeError):
            continue
    return {}


class InstagramScanner(OSINTScanner):
    _base_url = "https://www.instagram.com"

    def __init__(self, settings: AppSettings | None = None) -> None:
        self._settings = settings or AppSettings()

    async def scan(self, username: str) -> SocialProfile:
        url = f"{self._base_url}/{username}/"

        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
        }

        async with build_async_client(self._settings, extra_headers=headers) as client:
            response = await client.get(url)

        html = response.text or ""
        final_url = str(response.url)
        status = response.status_code

        # Instagram returns 200 for existing profiles, 404 for missing.
        # But it may also redirect to login pages for blocked requests.
        is_login_redirect = "/accounts/login" in final_url
        exists = status == 200 and not is_login_redirect and username.lower() in final_url.lower()

        metadata: dict[str, Any] = {
            "status_code": status,
            "final_url": final_url,
        }

        bio: str | None = None
        image_url: str | None = None

        if exists and html:
            # ── OG tags ──
            og_title = _extract_og_content(html, "og:title")
            og_desc = _extract_og_content(html, "og:description")
            og_image = _extract_og_content(html, "og:image")

            if og_title:
                metadata["og_title"] = og_title
            if og_desc:
                bio = og_desc
                counts = _parse_follower_counts(og_desc)
                metadata.update(counts)
            if og_image:
                image_url = og_image

            # ── JSON-LD ──
            ld_data = _parse_json_ld(html)
            if ld_data:
                ld_name = ld_data.get("name")
                if ld_name:
                    metadata["name"] = ld_name
                ld_desc = ld_data.get("description")
                if ld_desc and not bio:
                    bio = ld_desc
                ld_image = ld_data.get("image")
                if ld_image and not image_url:
                    image_url = ld_image if isinstance(ld_image, str) else None

                # mainEntity often has follower counts
                main_entity = ld_data.get("mainEntity")
                if isinstance(main_entity, dict):
                    interaction = main_entity.get("interactionStatistic")
                    if isinstance(interaction, list):
                        for stat in interaction:
                            if not isinstance(stat, dict):
                                continue
                            stat_type = stat.get("interactionType", "")
                            count = stat.get("userInteractionCount")
                            if "Follow" in str(stat_type):
                                metadata.setdefault("followers", count)

            # ── Title tag fallback ──
            title_match = re.search(r"<title>([^<]+)</title>", html, re.IGNORECASE)
            if title_match:
                metadata["title"] = title_match.group(1).strip()

        if is_login_redirect:
            metadata["blocked"] = True
            metadata["note"] = "Instagram redirected to login — try with residential proxy."

        return SocialProfile(
            url=f"{self._base_url}/{username}/",
            username=username,
            network_name="instagram",
            exists=exists,
            metadata=metadata,
            bio=bio,
            image_url=image_url,
        )
