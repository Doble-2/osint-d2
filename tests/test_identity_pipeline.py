"""Tests for the identity pipeline — pure utility functions.

Covers:
- sanitize_target_for_filename
- dedupe_profiles
- _strict_keep_profile (Sherlock heuristics)
- HuntRequest / PipelineResult data types
"""

from __future__ import annotations

import pytest

from core.domain.models import SocialProfile
from core.services.identity_pipeline import (
    HuntRequest,
    PipelineResult,
    SiteListOptions,
    dedupe_profiles,
    sanitize_target_for_filename,
    _strict_keep_profile,
)
from core.domain.models import PersonEntity


# ---------------------------------------------------------------------------
# sanitize_target_for_filename
# ---------------------------------------------------------------------------

class TestSanitizeTarget:
    def test_simple_username(self):
        assert sanitize_target_for_filename("doble-2") == "doble-2"

    def test_email_at_replaced(self):
        result = sanitize_target_for_filename("user@domain.com")
        assert "@" not in result
        assert "user_domain.com" == result

    def test_plus_replaced(self):
        result = sanitize_target_for_filename("user+tag")
        assert "+" not in result
        assert "user_tag" == result

    def test_spaces_replaced(self):
        result = sanitize_target_for_filename("hello world")
        assert " " not in result

    def test_empty_string_returns_target(self):
        assert sanitize_target_for_filename("") == "target"

    def test_only_special_chars_returns_target(self):
        assert sanitize_target_for_filename("!@#$%") == "target"

    def test_preserves_alphanumeric_and_dots(self):
        assert sanitize_target_for_filename("user.name_123") == "user.name_123"

    def test_unicode_handled(self):
        result = sanitize_target_for_filename("ángel")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_strips_leading_trailing_dashes(self):
        result = sanitize_target_for_filename("--user--")
        assert result == "user"


# ---------------------------------------------------------------------------
# dedupe_profiles
# ---------------------------------------------------------------------------

class TestDedupeProfiles:
    def _make_profile(self, *, network: str, username: str, url: str, exists: bool = True) -> SocialProfile:
        return SocialProfile(
            url=url,
            username=username,
            network_name=network,
            exists=exists,
        )

    def test_no_duplicates_unchanged(self):
        profiles = [
            self._make_profile(network="github", username="a", url="https://github.com/a"),
            self._make_profile(network="x", username="a", url="https://x.com/a"),
        ]
        result = dedupe_profiles(profiles)
        assert len(result) == 2

    def test_exact_duplicates_removed(self):
        p = self._make_profile(network="github", username="a", url="https://github.com/a")
        result = dedupe_profiles([p, p, p])
        assert len(result) == 1

    def test_same_network_different_url_kept(self):
        profiles = [
            self._make_profile(network="github", username="a", url="https://github.com/a"),
            self._make_profile(network="github", username="a", url="https://github.com/a/repos"),
        ]
        result = dedupe_profiles(profiles)
        assert len(result) == 2

    def test_same_network_same_url_different_user_kept(self):
        profiles = [
            self._make_profile(network="github", username="a", url="https://github.com/a"),
            self._make_profile(network="github", username="b", url="https://github.com/a"),
        ]
        result = dedupe_profiles(profiles)
        assert len(result) == 2

    def test_empty_list(self):
        assert dedupe_profiles([]) == []

    def test_preserves_order(self):
        profiles = [
            self._make_profile(network="x", username="u", url="https://x.com/u"),
            self._make_profile(network="github", username="u", url="https://github.com/u"),
            self._make_profile(network="x", username="u", url="https://x.com/u"),  # dup
        ]
        result = dedupe_profiles(profiles)
        assert len(result) == 2
        assert result[0].network_name == "x"
        assert result[1].network_name == "github"


# ---------------------------------------------------------------------------
# _strict_keep_profile — Sherlock heuristics
# ---------------------------------------------------------------------------

class TestStrictKeepProfile:
    def _sherlock_profile(
        self,
        *,
        network: str,
        username: str,
        final_url: str | None = None,
        exists: bool = True,
    ) -> SocialProfile:
        md = {"source": "sherlock"}
        if final_url:
            md["final_url"] = final_url
        return SocialProfile(
            url=final_url or f"https://{network}.com/{username}",
            username=username,
            network_name=network,
            exists=exists,
            metadata=md,
        )

    def test_non_sherlock_always_kept(self):
        p = SocialProfile(
            url="https://github.com/u",
            username="u",
            network_name="github",
            exists=True,
            metadata={"source": "builtin"},
        )
        assert _strict_keep_profile(profile=p, username="u") is True

    def test_sherlock_valid_url_kept(self):
        p = self._sherlock_profile(
            network="reddit",
            username="doble2",
            final_url="https://reddit.com/user/doble2",
        )
        assert _strict_keep_profile(profile=p, username="doble2") is True

    def test_sherlock_login_url_rejected(self):
        p = self._sherlock_profile(
            network="somesite",
            username="doble2",
            final_url="https://somesite.com/login?redirect=/doble2",
        )
        assert _strict_keep_profile(profile=p, username="doble2") is False

    def test_sherlock_consent_url_rejected(self):
        p = self._sherlock_profile(
            network="somesite",
            username="u",
            final_url="https://somesite.com/consent?u=doble2",
        )
        assert _strict_keep_profile(profile=p, username="u") is False

    def test_sherlock_denied_network_rejected(self):
        p = self._sherlock_profile(
            network="fanpop",
            username="doble2",
            final_url="https://fanpop.com/doble2",
        )
        assert _strict_keep_profile(profile=p, username="doble2") is False

    def test_not_exists_rejected(self):
        p = self._sherlock_profile(network="x", username="u", exists=False)
        assert _strict_keep_profile(profile=p, username="u") is False

    def test_username_not_in_url_checks_title(self):
        p = SocialProfile(
            url="https://somesite.com/profile/12345",
            username="doble2",
            network_name="somesite",
            exists=True,
            metadata={
                "source": "sherlock",
                "final_url": "https://somesite.com/profile/12345",
                "title": "doble2's profile page",
            },
        )
        assert _strict_keep_profile(profile=p, username="doble2") is True


# ---------------------------------------------------------------------------
# Data type construction
# ---------------------------------------------------------------------------

class TestDataTypes:
    def test_hunt_request_defaults(self):
        req = HuntRequest()
        assert req.usernames is None
        assert req.emails is None
        assert req.use_sherlock is False
        assert req.strict is False
        assert req.site_lists.enabled is False

    def test_hunt_request_with_values(self):
        req = HuntRequest(
            usernames=["doble-2"],
            emails=["test@test.com"],
            use_sherlock=True,
            strict=True,
        )
        assert req.usernames == ["doble-2"]
        assert req.use_sherlock is True

    def test_pipeline_result_has_person(self):
        person = PersonEntity(target="test")
        result = PipelineResult(person=person, usernames=["test"], emails=[])
        assert result.person.target == "test"
        assert result.warnings == []

    def test_site_list_options_defaults(self):
        opts = SiteListOptions()
        assert opts.enabled is False
        assert opts.username_path is None
