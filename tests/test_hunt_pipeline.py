"""Tests for the hunt() pipeline orchestration (issue #32).

Covers:
- Expansion loop: discovers new emails/usernames from scan results
- Loop termination when nothing new is found
- Sherlock integration path
- Site-list integration path
- Deduplication
- Breach check integration
- Hooks (warning callbacks)
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.config import AppSettings
from core.domain.models import SocialProfile
from core.services.identity_pipeline import (
    HuntRequest,
    PipelineHooks,
    SiteListOptions,
    hunt,
)


def _profile(*, network: str, username: str, exists: bool = True, **extra_meta) -> SocialProfile:
    return SocialProfile(
        url=f"https://{network}.com/{username}",
        username=username,
        network_name=network,
        exists=exists,
        metadata={"source": "test", **extra_meta},
    )


# ---------------------------------------------------------------------------
# Expansion loop
# ---------------------------------------------------------------------------

class TestExpansionLoop:
    """Verify that hunt() discovers new emails/usernames from scan results
    and re-scans them in subsequent rounds."""

    @pytest.mark.asyncio
    async def test_expansion_discovers_new_usernames(self):
        """When a scanner result contains other_users, those are scanned
        in the next round."""
        round_counter = {"count": 0}

        class FakeScanner:
            """Returns a profile with other_users on the first round only."""
            async def scan(self, value: str):
                round_counter["count"] += 1
                meta = {"source": "test"}
                if value == "primary" and round_counter["count"] <= 20:
                    meta["other_users"] = ["discovered_user"]
                return SocialProfile(
                    url=f"https://fake.com/{value}",
                    username=value,
                    network_name="fake",
                    exists=True,
                    metadata=meta,
                )

        with patch(
            "core.services.identity_pipeline._USERNAME_SCANNERS",
            (type(FakeScanner()),),
        ), patch(
            "core.services.identity_pipeline._EMAIL_SCANNERS",
            (),
        ):
            settings = AppSettings()
            request = HuntRequest(
                usernames=["primary"],
                emails=[],
                scan_localpart=False,
                use_sherlock=False,
            )
            result = await hunt(settings=settings, request=request)

        # Should have scanned both "primary" and "discovered_user"
        scanned_users = {p.username for p in result.person.profiles}
        assert "primary" in scanned_users
        assert "discovered_user" in scanned_users

    @pytest.mark.asyncio
    async def test_expansion_terminates_when_nothing_new(self):
        """The loop should terminate when no new usernames/emails are found."""

        class StableScanner:
            async def scan(self, value: str):
                return SocialProfile(
                    url=f"https://stable.com/{value}",
                    username=value,
                    network_name="stable",
                    exists=True,
                    metadata={"source": "test"},
                )

        with patch(
            "core.services.identity_pipeline._USERNAME_SCANNERS",
            (type(StableScanner()),),
        ), patch(
            "core.services.identity_pipeline._EMAIL_SCANNERS",
            (),
        ):
            settings = AppSettings()
            request = HuntRequest(
                usernames=["user1"],
                emails=[],
                scan_localpart=False,
                use_sherlock=False,
            )
            result = await hunt(settings=settings, request=request)

        # Should have exactly 1 profile — no expansion happened
        assert len(result.person.profiles) == 1


# ---------------------------------------------------------------------------
# Sherlock integration
# ---------------------------------------------------------------------------

class TestSherlockIntegration:
    @pytest.mark.asyncio
    async def test_sherlock_called_when_enabled(self):
        """When use_sherlock=True and a manifest is provided, run_sherlock_username is called."""

        mock_sherlock = AsyncMock(return_value=[
            _profile(network="reddit", username="testuser"),
        ])

        class EmptyScanner:
            async def scan(self, value: str):
                return SocialProfile(
                    url=f"https://empty.com/{value}",
                    username=value,
                    network_name="empty",
                    exists=False,
                    metadata={},
                )

        with patch(
            "core.services.identity_pipeline._USERNAME_SCANNERS",
            (type(EmptyScanner()),),
        ), patch(
            "core.services.identity_pipeline._EMAIL_SCANNERS",
            (),
        ), patch(
            "core.services.identity_pipeline.run_sherlock_username",
            mock_sherlock,
        ), patch(
            "core.services.identity_pipeline.load_sherlock_data",
            return_value={"TestSite": {"url": "http://test/{}", "errorType": "status_code"}},
        ):
            settings = AppSettings()
            request = HuntRequest(
                usernames=["testuser"],
                emails=[],
                scan_localpart=False,
                use_sherlock=True,
            )
            result = await hunt(settings=settings, request=request)

        mock_sherlock.assert_called_once()
        # Sherlock profile should be in results
        networks = {p.network_name for p in result.person.profiles}
        assert "reddit" in networks


# ---------------------------------------------------------------------------
# Site-list integration
# ---------------------------------------------------------------------------

class TestSiteListIntegration:
    @pytest.mark.asyncio
    async def test_warning_when_path_missing(self):
        """When site-list path doesn't exist, a warning is emitted."""
        warnings_received = []

        class EmptyScanner:
            async def scan(self, value: str):
                return SocialProfile(
                    url=f"https://e.com/{value}",
                    username=value,
                    network_name="e",
                    exists=False,
                    metadata={},
                )

        with patch(
            "core.services.identity_pipeline._USERNAME_SCANNERS",
            (type(EmptyScanner()),),
        ), patch(
            "core.services.identity_pipeline._EMAIL_SCANNERS",
            (),
        ), patch(
            "core.services.identity_pipeline.get_default_list_path",
            return_value=None,
        ):
            settings = AppSettings()
            hooks = PipelineHooks(
                warning=lambda msg: warnings_received.append(msg),
            )
            request = HuntRequest(
                usernames=["user"],
                emails=[],
                scan_localpart=False,
                use_sherlock=False,
                site_lists=SiteListOptions(
                    enabled=True,
                    username_path=Path("/nonexistent/path.json"),
                ),
            )
            await hunt(settings=settings, request=request, hooks=hooks)

        assert len(warnings_received) >= 1
        assert "not configured" in warnings_received[0].lower() or "missing" in warnings_received[0].lower()


# ---------------------------------------------------------------------------
# Breach check integration
# ---------------------------------------------------------------------------

class TestBreachCheckIntegration:
    @pytest.mark.asyncio
    async def test_breach_check_called_when_enabled(self):
        """When use_breach_check=True, enrich_profiles_with_breach_data is called."""

        breach_profile = _profile(network="hibp", username="test@test.com")
        mock_breach = MagicMock(return_value=[breach_profile])

        class EmptyScanner:
            async def scan(self, value: str):
                return SocialProfile(
                    url=f"https://e.com/{value}",
                    username=value,
                    network_name="e",
                    exists=False,
                    metadata={},
                )

        with patch(
            "core.services.identity_pipeline._USERNAME_SCANNERS",
            (),
        ), patch(
            "core.services.identity_pipeline._EMAIL_SCANNERS",
            (type(EmptyScanner()),),
        ), patch(
            "adapters.breach_check.enrich_profiles_with_breach_data",
            mock_breach,
        ):
            settings = AppSettings()
            request = HuntRequest(
                usernames=[],
                emails=["test@test.com"],
                scan_localpart=False,
                use_sherlock=False,
                use_breach_check=True,
            )
            await hunt(settings=settings, request=request)

        mock_breach.assert_called_once_with(emails=["test@test.com"])


# ---------------------------------------------------------------------------
# Deduplication in pipeline
# ---------------------------------------------------------------------------

class TestPipelineDeduplication:
    @pytest.mark.asyncio
    async def test_duplicate_profiles_are_removed(self):
        """If two scanners return the same profile, hunt() deduplicates."""

        class DuplicateScanner:
            async def scan(self, value: str):
                return SocialProfile(
                    url="https://github.com/user",
                    username="user",
                    network_name="github",
                    exists=True,
                    metadata={},
                )

        with patch(
            "core.services.identity_pipeline._USERNAME_SCANNERS",
            (type(DuplicateScanner()), type(DuplicateScanner())),
        ), patch(
            "core.services.identity_pipeline._EMAIL_SCANNERS",
            (),
        ):
            settings = AppSettings()
            request = HuntRequest(
                usernames=["user"],
                emails=[],
                scan_localpart=False,
                use_sherlock=False,
            )
            result = await hunt(settings=settings, request=request)

        github_profiles = [p for p in result.person.profiles if p.network_name == "github"]
        assert len(github_profiles) == 1
