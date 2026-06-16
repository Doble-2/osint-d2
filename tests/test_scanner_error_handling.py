"""Tests for scanner error handling and observability (issue #34).

Covers:
- safe_scan error fallback path (previously # pragma: no cover)
- Sherlock runner error counting
- Site-list runner error counting
- PipelineResult.scan_errors tracking
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from core.config import AppSettings
from core.services.identity_pipeline import PipelineResult, hunt, HuntRequest
from core.domain.models import PersonEntity


# ---------------------------------------------------------------------------
# PipelineResult.scan_errors field
# ---------------------------------------------------------------------------

class TestPipelineResultScanErrors:
    def test_default_zero(self):
        result = PipelineResult(
            person=PersonEntity(target="test"),
            usernames=["test"],
            emails=[],
        )
        assert result.scan_errors == 0

    def test_can_set_errors(self):
        result = PipelineResult(
            person=PersonEntity(target="test"),
            usernames=["test"],
            emails=[],
            scan_errors=5,
        )
        assert result.scan_errors == 5


# ---------------------------------------------------------------------------
# safe_scan error fallback (previously # pragma: no cover)
# ---------------------------------------------------------------------------

class TestSafeScanErrorFallback:
    """Verify that safe_scan catches exceptions and returns a fallback profile
    with exists=False and error metadata."""

    @pytest.mark.asyncio
    async def test_safe_scan_catches_scanner_error(self):
        """When a scanner raises, safe_scan should return a profile with
        exists=False and error in metadata."""

        class FailingScanner:
            """A scanner that always raises."""
            async def scan(self, value: str):
                raise ConnectionError("simulated network failure")

        # Import the function indirectly by running a minimal pipeline
        # with a patched scanner list
        scanner = FailingScanner()

        # We test safe_scan indirectly via the identity_pipeline.hunt
        # by mocking _USERNAME_SCANNERS
        with patch(
            "core.services.identity_pipeline._USERNAME_SCANNERS",
            (type(scanner),),
        ), patch(
            "core.services.identity_pipeline._EMAIL_SCANNERS",
            (),
        ):
            settings = AppSettings()
            request = HuntRequest(
                usernames=["testuser"],
                emails=[],
                scan_localpart=False,
                use_sherlock=False,
            )
            result = await hunt(settings=settings, request=request)

        # The failing scanner should have produced a profile with error metadata
        error_profiles = [
            p for p in result.person.profiles
            if isinstance(p.metadata, dict) and p.metadata.get("error")
        ]
        assert len(error_profiles) >= 1
        assert error_profiles[0].exists is False
        assert "simulated network failure" in str(error_profiles[0].metadata["error"])
        assert result.scan_errors >= 1


# ---------------------------------------------------------------------------
# Sherlock runner error counting
# ---------------------------------------------------------------------------

class TestSherlockErrorCounting:
    @pytest.mark.asyncio
    async def test_returns_error_count(self):
        from adapters.sherlock_runner import run_sherlock_username

        # Create a manifest with one site that will fail (invalid URL)
        manifest = {
            "TestSite": {
                "url": "http://localhost:1/__NONEXISTENT__/{}",
                "errorType": "status_code",
                "urlMain": "http://localhost:1",
            },
        }
        settings = AppSettings()
        found, error_count = await run_sherlock_username(
            usernames=["testuser"],
            manifest=manifest,
            settings=settings,
            max_concurrency=5,
            no_nsfw=False,
        )
        # The request to localhost:1 should fail (connection refused)
        # so error_count should be 1 and found should be empty
        assert error_count >= 1
        assert isinstance(found, list)


# ---------------------------------------------------------------------------
# Site-list runner error counting
# ---------------------------------------------------------------------------

class TestSiteListErrorCounting:
    @pytest.mark.asyncio
    async def test_username_sites_returns_error_count(self):
        from adapters.site_lists.runner import run_username_sites
        from adapters.site_lists.models import UsernameSite

        sites = [
            UsernameSite(
                name="FailSite",
                uri_check="http://localhost:1/__NONEXISTENT__/{account}",
                e_code=404,
                e_string="not found",
                m_code=200,
                m_string=None,
                cat="test",
            ),
        ]
        settings = AppSettings()
        found, error_count = await run_username_sites(
            usernames=["testuser"],
            sites=sites,
            settings=settings,
            max_concurrency=5,
            categories=None,
            no_nsfw=False,
        )
        assert error_count >= 1
        assert isinstance(found, list)

    @pytest.mark.asyncio
    async def test_email_sites_returns_error_count(self):
        from adapters.site_lists.runner import run_email_sites
        from adapters.site_lists.models import EmailSite

        sites = [
            EmailSite(
                name="FailSite",
                uri_check="http://localhost:1/__NONEXISTENT__/{account}",
                e_code=404,
                e_string="not found",
                m_code=200,
                m_string=None,
                cat="test",
            ),
        ]
        settings = AppSettings()
        found, error_count = await run_email_sites(
            emails=["test@test.com"],
            sites=sites,
            settings=settings,
            max_concurrency=5,
            categories=None,
            no_nsfw=False,
        )
        assert error_count >= 1
        assert isinstance(found, list)
