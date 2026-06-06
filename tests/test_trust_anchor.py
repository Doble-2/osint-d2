"""Tests for the trust anchor verification system.

Covers:
- TrustAnchor parsing
- ReferenceIdentity building
- Name extraction from emails
- Profile verification scoring
- False positive filtering
"""

from __future__ import annotations

import pytest

from core.domain.models import SocialProfile
from core.services.trust_anchor import (
    ReferenceIdentity,
    TrustAnchor,
    VerificationResult,
    _extract_keywords,
    _extract_name_from_email,
    _hash_image_url,
    _normalize,
    build_reference_from_profiles,
    filter_profiles_by_trust,
    verify_profile,
)


# ---------------------------------------------------------------------------
# TrustAnchor parsing
# ---------------------------------------------------------------------------

class TestTrustAnchorParse:
    def test_instagram(self):
        a = TrustAnchor.parse("instagram:xkissmely")
        assert a.network == "instagram"
        assert a.username == "xkissmely"
        assert a.is_email is False

    def test_email(self):
        a = TrustAnchor.parse("email:test@gmail.com")
        assert a.network == "email"
        assert a.username == "test@gmail.com"
        assert a.is_email is True

    def test_github(self):
        a = TrustAnchor.parse("github:doble-2")
        assert a.network == "github"
        assert a.username == "doble-2"

    def test_case_insensitive_network(self):
        a = TrustAnchor.parse("INSTAGRAM:User")
        assert a.network == "instagram"

    def test_invalid_no_colon_raises(self):
        with pytest.raises(ValueError, match="Invalid trust anchor"):
            TrustAnchor.parse("justausername")

    def test_strips_whitespace(self):
        a = TrustAnchor.parse("  github : doble-2  ")
        assert a.network == "github"
        assert a.username == "doble-2"


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

class TestNormalize:
    def test_lowercase_and_strip(self):
        assert _normalize("  Hello World  ") == "hello world"

    def test_removes_special_chars(self):
        result = _normalize("Ángel's profile!")
        assert "'" not in result
        assert "!" not in result


class TestExtractKeywords:
    def test_filters_short_words(self):
        kw = _extract_keywords("I am a developer and I code")
        assert "am" not in kw
        assert "developer" in kw
        assert "code" in kw

    def test_filters_stop_words(self):
        kw = _extract_keywords("this is the best project for all")
        assert "this" not in kw
        assert "the" not in kw
        assert "best" in kw
        assert "project" in kw

    def test_empty_string(self):
        assert _extract_keywords("") == set()


class TestHashImageUrl:
    def test_same_url_same_hash(self):
        h1 = _hash_image_url("https://example.com/avatar.jpg")
        h2 = _hash_image_url("https://example.com/avatar.jpg")
        assert h1 == h2

    def test_different_url_different_hash(self):
        h1 = _hash_image_url("https://example.com/a.jpg")
        h2 = _hash_image_url("https://example.com/b.jpg")
        assert h1 != h2

    def test_returns_12_chars(self):
        h = _hash_image_url("https://example.com/img.png")
        assert len(h) == 12


class TestExtractNameFromEmail:
    def test_dot_separated(self):
        parts = _extract_name_from_email("kissmely.marcano@gmail.com")
        assert parts == ["kissmely", "marcano"]

    def test_underscore_separated(self):
        parts = _extract_name_from_email("john_doe@gmail.com")
        assert parts == ["john", "doe"]

    def test_hyphen_separated(self):
        parts = _extract_name_from_email("john-doe@gmail.com")
        assert parts == ["john", "doe"]

    def test_concatenated_with_hint(self):
        parts = _extract_name_from_email(
            "kissmelymarcano@gmail.com",
            known_usernames=["xkissmely"],
        )
        assert "kissmely" in parts
        assert "marcano" in parts

    def test_single_short_word(self):
        parts = _extract_name_from_email("joe@gmail.com")
        assert parts == ["joe"]

    def test_single_long_word_splits(self):
        parts = _extract_name_from_email("angelcalderon@gmail.com")
        assert len(parts) >= 2  # Should attempt to split


# ---------------------------------------------------------------------------
# ReferenceIdentity
# ---------------------------------------------------------------------------

class TestReferenceIdentity:
    def test_empty(self):
        ref = ReferenceIdentity()
        assert ref.is_empty() is True

    def test_not_empty_with_names(self):
        ref = ReferenceIdentity(names={"angel"})
        assert ref.is_empty() is False


# ---------------------------------------------------------------------------
# build_reference_from_profiles
# ---------------------------------------------------------------------------

class TestBuildReference:
    def _make_profile(self, **kwargs) -> SocialProfile:
        defaults = {
            "url": "https://example.com",
            "username": "user",
            "network_name": "github",
            "exists": True,
            "metadata": {},
        }
        defaults.update(kwargs)
        return SocialProfile(**defaults)

    def test_builds_from_email_anchor(self):
        anchors = [TrustAnchor.parse("email:kissmelymarcano@gmail.com")]
        ref = build_reference_from_profiles([], anchors)
        assert "kissmelymarcano@gmail.com" in ref.emails
        assert len(ref.names) > 0  # Should extract name from email

    def test_builds_from_network_anchor(self):
        profile = self._make_profile(
            network_name="instagram",
            username="xkissmely",
            metadata={"name": "Kissmely Marcano"},
            bio="Photographer and designer",
        )
        anchors = [TrustAnchor.parse("instagram:xkissmely")]
        ref = build_reference_from_profiles([profile], anchors)
        assert "instagram" in ref.trusted_networks
        assert any("kissmely" in n for n in ref.names)
        assert len(ref.bio_keywords) > 0

    def test_ignores_non_matching_profiles(self):
        profile = self._make_profile(
            network_name="github",
            username="someoneelse",
            metadata={"name": "Other Person"},
        )
        anchors = [TrustAnchor.parse("instagram:xkissmely")]
        ref = build_reference_from_profiles([profile], anchors)
        assert ref.is_empty()

    def test_extracts_avatar_hash(self):
        profile = self._make_profile(
            network_name="instagram",
            username="xkissmely",
            metadata={"name": "Kissmely"},
            image_url="https://cdn.instagram.com/avatar.jpg",
        )
        anchors = [TrustAnchor.parse("instagram:xkissmely")]
        ref = build_reference_from_profiles([profile], anchors)
        assert len(ref.avatar_hashes) == 1


# ---------------------------------------------------------------------------
# verify_profile
# ---------------------------------------------------------------------------

class TestVerifyProfile:
    def _make_ref(self, **kwargs) -> ReferenceIdentity:
        return ReferenceIdentity(**kwargs)

    def _make_profile(self, **kwargs) -> SocialProfile:
        defaults = {
            "url": "https://example.com",
            "username": "user",
            "network_name": "unknown",
            "exists": True,
            "metadata": {},
        }
        defaults.update(kwargs)
        return SocialProfile(**defaults)

    def test_empty_reference_returns_verified(self):
        ref = self._make_ref()
        profile = self._make_profile()
        result = verify_profile(profile, ref)
        assert result.verified is True
        assert result.confidence == 0.5

    def test_non_existing_profile_always_verified(self):
        ref = self._make_ref(names={"angel calderon"})
        profile = self._make_profile(exists=False)
        result = verify_profile(profile, ref)
        assert result.verified is True

    def test_trusted_profile_always_verified(self):
        ref = self._make_ref(
            names={"kissmely marcano"},
            trusted_networks={"instagram": "xkissmely"},
        )
        profile = self._make_profile(
            network_name="instagram",
            username="xkissmely",
        )
        result = verify_profile(profile, ref)
        assert result.verified is True
        assert result.confidence == 1.0

    def test_matching_name_high_confidence(self):
        ref = self._make_ref(names={"kissmely marcano"})
        profile = self._make_profile(
            metadata={"name": "Kissmely Marcano"},
        )
        result = verify_profile(profile, ref)
        assert result.verified is True
        assert result.confidence >= 0.8

    def test_contradicting_name_low_confidence(self):
        ref = self._make_ref(names={"kissmely marcano"})
        profile = self._make_profile(
            metadata={"name": "Kissmely Almonte"},
        )
        result = verify_profile(profile, ref)
        # "almonte" contradicts "marcano" — should flag
        assert result.confidence < 0.5

    def test_no_name_data_neutral(self):
        ref = self._make_ref(names={"angel"})
        profile = self._make_profile(metadata={})
        result = verify_profile(profile, ref)
        # No name data → neutral (shouldn't fail)
        assert result.verified is True


# ---------------------------------------------------------------------------
# filter_profiles_by_trust
# ---------------------------------------------------------------------------

class TestFilterProfilesByTrust:
    def _make_profile(self, **kwargs) -> SocialProfile:
        defaults = {
            "url": "https://example.com",
            "username": "user",
            "network_name": "unknown",
            "exists": True,
            "metadata": {},
        }
        defaults.update(kwargs)
        return SocialProfile(**defaults)

    def test_empty_reference_no_change(self):
        ref = ReferenceIdentity()
        profiles = [self._make_profile()]
        result = filter_profiles_by_trust(profiles, ref)
        assert len(result) == 1
        assert result[0].exists is True

    def test_non_verified_marked_false_when_remove(self):
        ref = ReferenceIdentity(names={"kissmely marcano"})
        profiles = [
            self._make_profile(
                network_name="pinterest",
                username="kissmely_almonte",
                metadata={"name": "Kissmely Almonte"},
            ),
        ]
        result = filter_profiles_by_trust(profiles, ref, remove=True)
        # Should be discarded (different name)
        assert result[0].exists is False
        assert result[0].metadata.get("trust_discarded") is True

    def test_annotates_without_removing_by_default(self):
        ref = ReferenceIdentity(names={"kissmely marcano"})
        profiles = [
            self._make_profile(
                metadata={"name": "Kissmely Almonte"},
            ),
        ]
        result = filter_profiles_by_trust(profiles, ref, remove=False)
        # Not removed, but annotated
        assert result[0].exists is True
        assert "trust_verified" in result[0].metadata
        assert "trust_confidence" in result[0].metadata
