"""Tests for profile_enricher with mocked HTTP (issue #32).

Covers:
- Enriches profile without bio/avatar from HTML metadata
- Skips non-existing profiles
- Skips profiles with existing bio
- Handles HTTP errors gracefully
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import httpx

from core.config import AppSettings
from core.domain.models import SocialProfile
from adapters.profile_enricher import enrich_profiles_from_html


def _mock_response(*, status_code: int = 200, text: str = "", url: str = "https://example.com") -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.text = text
    resp.url = httpx.URL(url)
    return resp


@asynccontextmanager
async def _mock_client_cm(response: MagicMock):
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    yield client


# ---------------------------------------------------------------------------
# Enriches profiles
# ---------------------------------------------------------------------------

class TestEnrichProfilesFromHTML:
    @pytest.mark.asyncio
    async def test_enriches_profile_without_bio(self):
        """Profile without bio gets bio from HTML meta description."""
        html = '<html><head><meta name="description" content="A developer"><meta property="og:image" content="https://img.com/avatar.jpg"></head></html>'
        resp = _mock_response(status_code=200, text=html, url="https://github.com/user")

        profile = SocialProfile(
            url="https://github.com/user",
            username="user",
            network_name="github",
            exists=True,
            metadata={},
        )

        with patch("adapters.profile_enricher.build_async_client", return_value=_mock_client_cm(resp)):
            await enrich_profiles_from_html(
                profiles=[profile],
                settings=AppSettings(),
            )

        assert profile.bio == "A developer"
        assert profile.image_url == "https://img.com/avatar.jpg"

    @pytest.mark.asyncio
    async def test_skips_non_existing_profiles(self):
        """Profiles with exists=False are not fetched."""
        profile = SocialProfile(
            url="https://github.com/nobody",
            username="nobody",
            network_name="github",
            exists=False,
            metadata={},
        )

        resp = _mock_response()

        with patch("adapters.profile_enricher.build_async_client", return_value=_mock_client_cm(resp)):
            await enrich_profiles_from_html(
                profiles=[profile],
                settings=AppSettings(),
            )

        # Bio should remain None — the enricher should have skipped it
        assert profile.bio is None

    @pytest.mark.asyncio
    async def test_skips_profiles_with_existing_bio(self):
        """Profiles that already have bio are not re-fetched."""
        profile = SocialProfile(
            url="https://github.com/user",
            username="user",
            network_name="github",
            exists=True,
            metadata={},
            bio="Already has a bio",
        )

        resp = _mock_response(
            text='<html><head><meta name="description" content="New bio"></head></html>',
        )

        with patch("adapters.profile_enricher.build_async_client", return_value=_mock_client_cm(resp)):
            await enrich_profiles_from_html(
                profiles=[profile],
                settings=AppSettings(),
            )

        # Bio should remain unchanged
        assert profile.bio == "Already has a bio"

    @pytest.mark.asyncio
    async def test_handles_http_error_gracefully(self):
        """HTTP 500 should not crash the enricher."""
        profile = SocialProfile(
            url="https://github.com/user",
            username="user",
            network_name="github",
            exists=True,
            metadata={},
        )

        resp = _mock_response(status_code=500)

        with patch("adapters.profile_enricher.build_async_client", return_value=_mock_client_cm(resp)):
            # Should not raise
            await enrich_profiles_from_html(
                profiles=[profile],
                settings=AppSettings(),
            )

        assert profile.bio is None

    @pytest.mark.asyncio
    async def test_handles_exception_gracefully(self):
        """Network exception should not crash the enricher."""
        profile = SocialProfile(
            url="https://github.com/user",
            username="user",
            network_name="github",
            exists=True,
            metadata={},
        )

        @asynccontextmanager
        async def failing_client(*args, **kwargs):
            client = AsyncMock()
            client.get = AsyncMock(side_effect=ConnectionError("simulated"))
            yield client

        with patch("adapters.profile_enricher.build_async_client", return_value=failing_client()):
            await enrich_profiles_from_html(
                profiles=[profile],
                settings=AppSettings(),
            )

        assert profile.bio is None
