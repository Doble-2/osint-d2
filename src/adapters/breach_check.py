from __future__ import annotations

import uuid
from typing import Iterable

import httpx

try:
    import tls_client  # type: ignore
except Exception:  # pragma: no cover
    tls_client = None  # type: ignore

from core.domain.models import (
    HaveibeenpwnedBreach,
    HaveibeenpwnedProfiles,
    SocialProfile,
)
from core.config import AppSettings


def _build_hibp_headers() -> dict[str, str]:
    """Generate fresh HIBP headers with random identifiers per request."""

    trace_id = uuid.uuid4().hex
    span_id = uuid.uuid4().hex[:16]
    return {
        "accept": "*/*",
        "priority": "u=1, i",
        "referer": "https://haveibeenpwned.com/",
        "request-id": f"|{trace_id}.{span_id}",
        "sec-ch-ua": '"Not(A:Brand";v="8", "Chromium";v="136", "Google Chrome";v="136"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "traceparent": f"00-{trace_id}-{span_id}-01",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
        ),
    }


def enrich_profiles_with_breach_data(
    emails: Iterable[str],
) -> list[SocialProfile]:
    settings = AppSettings()

    tls_session = None
    if tls_client is not None:
        try:
            tls_session = tls_client.Session(
                client_identifier="chrome_120",
                random_tls_extension_order=True,  # type: ignore[call-arg]
            )
        except Exception:
            tls_session = None

    httpx_client: httpx.Client | None = None
    if tls_session is None:
        httpx_client = httpx.Client(
            timeout=httpx.Timeout(settings.http_timeout_seconds),
            follow_redirects=True,
        )

    profiles: list[SocialProfile] = []
    try:
        for email in emails:
            unified_url = f"https://haveibeenpwned.com/unifiedsearch/{email}"

            status_code: int | None = None
            payload: object | None = None
            error: str | None = None
            headers = _build_hibp_headers()

            try:
                if tls_session is not None:
                    response = tls_session.get(unified_url, headers=headers)
                    status_code = response.status_code or 0
                    payload = response.json() if status_code == 200 else None
                else:
                    assert httpx_client is not None
                    response = httpx_client.get(unified_url, headers=headers)
                    status_code = response.status_code
                    payload = response.json() if status_code == 200 else None
            except OSError:
                # Some tls_client wheels depend on musl (libc.musl-*.so.1).
                # If the runtime loader fails, fall back to httpx instead of crashing.
                try:
                    if httpx_client is None:
                        httpx_client = httpx.Client(
                            timeout=httpx.Timeout(settings.http_timeout_seconds),
                            follow_redirects=True,
                        )
                    response = httpx_client.get(unified_url, headers=headers)
                    status_code = response.status_code
                    payload = response.json() if status_code == 200 else None
                except Exception:
                    error = "hibp_request_failed_oserror"
                    continue
            except Exception:
                error = "hibp_request_failed"
                continue

            if status_code != 200 or not isinstance(payload, dict):
                profiles.append(
                    SocialProfile(
                        url=unified_url,
                        username=email,
                        network_name="hibp",
                        exists=False,
                        metadata={
                            "source": "haveibeenpwned_unifiedsearch",
                            "status_code": status_code,
                            "error": error or (f"hibp_http_{status_code}" if status_code else "hibp_no_response"),
                        },
                    )
                )
                continue

            raw_breaches = payload.get("Breaches", [])
            breaches: list[HaveibeenpwnedBreach] = []
            if isinstance(raw_breaches, list):
                for breach_data in raw_breaches:
                    if not isinstance(breach_data, dict):
                        continue
                    try:
                        breaches.append(HaveibeenpwnedBreach(**breach_data))
                    except Exception:
                        continue

            hibp = HaveibeenpwnedProfiles(email=email, breaches=breaches)
            profiles.append(
                SocialProfile(
                    url=unified_url,
                    username=email,
                    network_name="hibp",
                    exists=True,
                    metadata={
                        "source": "haveibeenpwned_unifiedsearch",
                        "status_code": status_code,
                        "breach_count": len(breaches),
                        "breaches": hibp.model_dump(mode="json"),
                    },
                )
            )
    finally:
        if httpx_client is not None:
            httpx_client.close()

    return profiles
