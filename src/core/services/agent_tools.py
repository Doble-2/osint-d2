"""Agent tool definitions and execution dispatcher.

Each tool wraps an existing OSINT scanner/pipeline and exposes it as
an OpenAI function-calling tool.  Results are compacted to fit within
the LLM context window.
"""

from __future__ import annotations

import json
from typing import Any

from adapters.breach_check import enrich_profiles_with_breach_data
from core.config import AppSettings
from core.domain.models import SocialProfile
from core.services.identity_pipeline import (
    scan_email,
    scan_username,
)


# ---------------------------------------------------------------------------
# OpenAI tool schemas
# ---------------------------------------------------------------------------

AGENT_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "scan_username",
            "description": (
                "Scan a username across 18+ social networks (GitHub, GitLab, X, "
                "Reddit, Telegram, etc.). Returns a list of confirmed profiles "
                "with metadata, bios, and avatar URLs."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "username": {
                        "type": "string",
                        "description": "The username/handle to investigate.",
                    },
                },
                "required": ["username"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scan_email",
            "description": (
                "Scan an email address across Gravatar, PGP keyservers, and "
                "Ubuntu keyserver.  Optionally pivots the local part as a "
                "username across social networks."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "email": {
                        "type": "string",
                        "description": "The email address to investigate.",
                    },
                    "scan_localpart": {
                        "type": "boolean",
                        "description": (
                            "If true, also scan the local part (before @) as "
                            "a username on social networks."
                        ),
                        "default": True,
                    },
                },
                "required": ["email"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "breach_check",
            "description": (
                "Check an email against HaveIBeenPwned to find data breaches. "
                "Returns breach names, dates, and compromised data types."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "email": {
                        "type": "string",
                        "description": "The email address to check for breaches.",
                    },
                },
                "required": ["email"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": (
                "Fetch a URL (website, blog, portfolio) and extract intelligence: "
                "page title, meta description, emails found in the page, social "
                "media links with usernames (GitHub, Twitter, LinkedIn, Instagram, "
                "etc.), and external links. Use this when you find a personal "
                "website, blog, or portfolio URL in scan results."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The full URL to fetch (e.g. https://angelcalderon.dev).",
                    },
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_report",
            "description": (
                "FINAL STEP: Call this when you have gathered enough evidence. "
                "Submit your analysis as a structured report. This ends the "
                "investigation."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": (
                            "Detailed Markdown report with the 6 analysis "
                            "sections (Identity, Geo-temporal, Psychological, "
                            "Technical, Ideology, Attack Surface)."
                        ),
                    },
                    "highlights": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "3-5 key deductions from the evidence.",
                    },
                    "confidence": {
                        "type": "number",
                        "description": "Confidence level from 0.0 to 1.0.",
                    },
                },
                "required": ["summary", "highlights", "confidence"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------

def _compact_profiles(profiles: list[SocialProfile], *, max_profiles: int = 30) -> list[dict[str, Any]]:
    """Convert profiles to a compact JSON-friendly format for the LLM."""
    out: list[dict[str, Any]] = []
    for p in profiles[:max_profiles]:
        entry: dict[str, Any] = {
            "network": p.network_name,
            "username": p.username,
            "exists": p.exists,
            "url": p.url,
        }
        if p.bio:
            entry["bio"] = p.bio[:300]
        if p.image_url:
            entry["avatar"] = p.image_url

        # Extract useful metadata fields without dumping everything.
        meta = p.metadata if isinstance(p.metadata, dict) else {}
        for key in (
            "name", "location", "company", "blog", "email",
            "followers", "following", "public_repos",
            "twitter_username", "created_at",
            "other_emails", "other_users", "other_websites",
            "description", "title",
        ):
            val = meta.get(key)
            if val is not None and val != "" and val != []:
                entry[key] = val

        # Breach data
        breaches = meta.get("breaches")
        if isinstance(breaches, dict):
            entry["breaches"] = breaches

        out.append(entry)
    return out


async def execute_tool(
    name: str,
    arguments: dict[str, Any],
    *,
    settings: AppSettings,
    enable_breach_check: bool = False,
) -> str:
    """Execute an agent tool and return a JSON string result.

    Parameters
    ----------
    name:
        Tool name (must match one of AGENT_TOOLS).
    arguments:
        Parsed arguments from the LLM tool call.
    settings:
        Application settings (proxy, timeouts, etc.).
    enable_breach_check:
        Whether breach_check tool is allowed.

    Returns
    -------
    A JSON string to inject as a ``tool`` message.
    """
    if name == "scan_username":
        username = arguments.get("username", "")
        if not username:
            return json.dumps({"error": "username is required"})
        result = await scan_username(settings=settings, username=username)
        profiles = _compact_profiles(list(result.person.profiles))
        confirmed = [p for p in profiles if p.get("exists")]
        return json.dumps({
            "target": username,
            "total_scanned": len(profiles),
            "confirmed": len(confirmed),
            "profiles": profiles,
        }, ensure_ascii=False)

    if name == "scan_email":
        email = arguments.get("email", "")
        if not email:
            return json.dumps({"error": "email is required"})
        do_localpart = arguments.get("scan_localpart", True)
        result = await scan_email(
            settings=settings,
            email=email,
            scan_localpart=do_localpart,
        )
        profiles = _compact_profiles(list(result.person.profiles))
        confirmed = [p for p in profiles if p.get("exists")]
        return json.dumps({
            "target": email,
            "total_scanned": len(profiles),
            "confirmed": len(confirmed),
            "profiles": profiles,
        }, ensure_ascii=False)

    if name == "breach_check":
        email = arguments.get("email", "")
        if not email:
            return json.dumps({"error": "email is required"})
        if not enable_breach_check:
            return json.dumps({
                "error": "breach_check is disabled. User must enable with --breach-check.",
            })
        breach_profiles = enrich_profiles_with_breach_data([email])
        profiles = _compact_profiles(breach_profiles)
        return json.dumps({
            "target": email,
            "results": profiles,
        }, ensure_ascii=False)

    if name == "fetch_url":
        url = arguments.get("url", "")
        if not url:
            return json.dumps({"error": "url is required"})
        if not (url.startswith("http://") or url.startswith("https://")):
            url = f"https://{url}"

        # SSRF guard — block private/internal/IMDS targets (issue #25)
        from core.services.url_guard import SSRFBlockedError, validate_url
        try:
            url = validate_url(url)
        except (SSRFBlockedError, ValueError) as exc:
            return json.dumps({"url": url, "error": f"SSRF blocked: {exc}"})

        from adapters.http_client import build_async_client, extract_html_metadata
        try:
            async with build_async_client(settings) as client:
                resp = await client.get(url)
            if resp.status_code >= 400:
                return json.dumps({
                    "url": url,
                    "error": f"HTTP {resp.status_code}",
                })
            html = resp.text or ""
            meta = extract_html_metadata(html=html, base_url=str(resp.url))
            return json.dumps({
                "url": str(resp.url),
                "status_code": resp.status_code,
                **meta,
            }, ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"url": url, "error": str(exc)})

    if name == "generate_report":
        # This is handled by the engine — just echo back.
        return json.dumps({"status": "report_generated"})

    return json.dumps({"error": f"Unknown tool: {name}"})
