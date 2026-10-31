"""Agent tool definitions and execution dispatcher.

Each tool wraps an existing OSINT scanner/pipeline and exposes it as
an OpenAI function-calling tool.  Results are compacted to fit within
the LLM context window.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from urllib.parse import urljoin

import httpx

from adapters.http_client import get_limited
from adapters.breach_check import enrich_profiles_with_breach_data
from core.config import AppSettings
from core.domain.models import SocialProfile
from adapters.vector_store import VectorStore
from adapters.avatar_analyzer import AvatarAnalyzer
from adapters.phone_scanner import PhoneScanner
from core.services.identity_pipeline import (
    scan_email,
    scan_username,
)
from core.services.url_guard import SSRFBlockedError, validate_url

_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_MAX_REDIRECTS = 5
_MAX_HTML_CHARS = 2_000_000
_MAX_VECTOR_RESULTS = 20


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
                "Check an email with the official HaveIBeenPwned API to find data breaches. "
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
                        "description": "The full URL to fetch (e.g. https://example.com/portfolio).",
                    },
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_avatars",
            "description": (
                "Compare two avatar image URLs using perceptual hashing (dHash). "
                "Detects if both accounts use the same photo even if resized or recompressed."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "avatar_url_1": {
                        "type": "string",
                        "description": "First image URL.",
                    },
                    "avatar_url_2": {
                        "type": "string",
                        "description": "Second image URL.",
                    },
                },
                "required": ["avatar_url_1", "avatar_url_2"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scan_phone",
            "description": (
                "Investigate a phone number. Validates E.164 standard, identifies carrier, "
                "country, line type (mobile/voip/fixed), timezones, active WhatsApp status, "
                "and generates reverse lookup footprints (Telegram, Truecaller, Sync.me, dorks)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "phone_number": {
                        "type": "string",
                        "description": "Phone number in international or local format (e.g. +12125551234, +442071234567).",
                    },
                },
                "required": ["phone_number"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_vector_memory",
            "description": (
                "Search in-memory vector database containing previously scraped web pages, "
                "bios, and snippets using semantic concept similarity."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Semantic query or topic to search for in collected evidence.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of snippets to retrieve (default 3).",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "correlate_stylometry",
            "description": (
                "Compare a suspect text sample or anonymous post against known target writing styles "
                "using character n-gram stylometry. Returns similarity score (0.0 to 1.0)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sample_text": {
                        "type": "string",
                        "description": "Text sample from an anonymous or suspect account to correlate.",
                    },
                },
                "required": ["sample_text"],
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
                            "Detailed Markdown report with the sections the "
                            "system prompt requires."
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
    # Confirmed profiles first, so the cap never drops real findings.
    ordered = sorted(profiles, key=lambda p: not p.exists)
    for p in ordered[:max_profiles]:
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

        # A failed lookup must not read as "nothing found".
        if isinstance(meta.get("error"), str):
            entry["error"] = meta["error"]

        # Breach data
        breaches = meta.get("breaches")
        if isinstance(breaches, dict):
            entry["breaches"] = breaches

        out.append(entry)
    return out


def _scan_result_json(target: str, profiles: list[SocialProfile]) -> str:
    return json.dumps({
        "target": target,
        "total_scanned": len(profiles),
        "confirmed": sum(1 for p in profiles if p.exists),
        "profiles": _compact_profiles(profiles),
    }, ensure_ascii=False)


async def _guarded_get(client: httpx.AsyncClient, url: str) -> httpx.Response:
    """GET *url* validating every redirect hop against the SSRF guard.

    The URLs come from the LLM, which reads attacker-controlled pages, and a
    public URL can simply redirect to an internal address.
    """
    for _ in range(_MAX_REDIRECTS + 1):
        await asyncio.to_thread(validate_url, url)
        resp = await get_limited(client, url, follow_redirects=False)
        location = resp.headers.get("location") if resp.status_code in _REDIRECT_STATUSES else None
        if not location:
            return resp
        url = urljoin(str(resp.url), location)
    raise ValueError(f"Too many redirects (>{_MAX_REDIRECTS})")


async def execute_tool(
    name: str,
    arguments: dict[str, Any],
    *,
    settings: AppSettings,
    enable_breach_check: bool = False,
    vector_store: VectorStore | None = None,
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
        return _scan_result_json(username, list(result.person.profiles))

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
        return _scan_result_json(email, list(result.person.profiles))

    if name == "breach_check":
        email = arguments.get("email", "")
        if not email:
            return json.dumps({"error": "email is required"})
        if not enable_breach_check:
            return json.dumps({
                "error": "breach_check is disabled. User must enable with --breach-check.",
            })
        breach_profiles = await asyncio.to_thread(enrich_profiles_with_breach_data, [email], settings=settings)
        profiles = _compact_profiles(breach_profiles)
        output: dict[str, Any] = {"target": email, "results": profiles}
        errors = [p["error"] for p in profiles if p.get("error")]
        if errors:
            output["error"] = f"Breach data unavailable, nothing was checked: {errors[0]}"
        return json.dumps(output, ensure_ascii=False)

    if name == "fetch_url":
        url = arguments.get("url", "")
        if not url:
            return json.dumps({"error": "url is required"})
        if not (url.startswith("http://") or url.startswith("https://")):
            url = f"https://{url}"

        from adapters.http_client import build_async_client, extract_html_metadata
        try:
            # SSRF guard — block private/internal/IMDS targets (issue #25)
            async with build_async_client(settings) as client:
                resp = await _guarded_get(client, url)
            if resp.status_code >= 400:
                return json.dumps({
                    "url": url,
                    "error": f"HTTP {resp.status_code}",
                })
            html = (resp.text or "")[:_MAX_HTML_CHARS]
            meta = await asyncio.to_thread(extract_html_metadata, html=html, base_url=str(resp.url))
            return json.dumps({
                "url": str(resp.url),
                "status_code": resp.status_code,
                **meta,
            }, ensure_ascii=False)
        except (SSRFBlockedError, ValueError) as exc:
            return json.dumps({"url": url, "error": f"SSRF blocked: {exc}"})
        except Exception as exc:
            return json.dumps({"url": url, "error": str(exc)})

    if name == "compare_avatars":
        url1 = arguments.get("avatar_url_1", "")
        url2 = arguments.get("avatar_url_2", "")
        if not url1 or not url2:
            return json.dumps({"error": "Both avatar_url_1 and avatar_url_2 are required."})

        try:
            from adapters.http_client import build_async_client
            async with build_async_client(settings=settings) as client:
                resp1 = await _guarded_get(client, url1)
                resp2 = await _guarded_get(client, url2)
                if resp1.status_code != 200 or resp2.status_code != 200:
                    return json.dumps({
                        "error": f"Failed fetching avatars: img1={resp1.status_code}, img2={resp2.status_code}"
                    })
                comp = await asyncio.to_thread(AvatarAnalyzer.compare_avatars, resp1.content, resp2.content)
                return json.dumps(comp, ensure_ascii=False)
        except (SSRFBlockedError, ValueError) as exc:
            return json.dumps({"error": f"SSRF blocked: {exc}"})
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    if name == "scan_phone":
        phone_num = arguments.get("phone_number", "")
        if not phone_num:
            return json.dumps({"error": "phone_number is required"})
        res = await PhoneScanner.scan(phone_number=phone_num, settings=settings)
        return json.dumps({
            "e164": res.e164,
            "is_valid": res.is_valid,
            "country": res.country_name,
            "country_iso": res.country_iso,
            "carrier": res.carrier_name,
            "line_type": res.line_type,
            "timezones": res.timezones,
            "whatsapp_active": res.whatsapp_active,
            "associated_names": res.associated_names,
            "associated_usernames": res.associated_usernames,
            "footprint_urls": res.footprint_urls,
            "error": res.error,
        }, ensure_ascii=False)

    if name == "search_vector_memory":
        if not vector_store:
            return json.dumps({"error": "Vector store not initialized or empty."})
        query = arguments.get("query", "")
        try:
            limit = max(1, min(int(arguments.get("limit", 3)), _MAX_VECTOR_RESULTS))
        except (TypeError, ValueError):
            limit = 3
        results = vector_store.search_semantic(query=query, limit=limit)
        return json.dumps({"query": query, "results": results}, ensure_ascii=False)

    if name == "correlate_stylometry":
        if not vector_store:
            return json.dumps({"error": "Vector store not initialized or empty."})
        sample = arguments.get("sample_text", "")
        matches = vector_store.correlate_author_style(sample_text=sample)
        return json.dumps({"sample_length": len(sample), "stylometric_matches": matches}, ensure_ascii=False)

    if name == "generate_report":
        # This is handled by the engine — just echo back.
        return json.dumps({"status": "report_generated"})

    return json.dumps({"error": f"Unknown tool: {name}"})
