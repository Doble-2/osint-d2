"""Tests for core domain models (SocialProfile, PersonEntity, AnalysisReport)."""

from __future__ import annotations

import json

import pytest
from core.domain.models import AnalysisReport, PersonEntity, SocialProfile


# ---------------------------------------------------------------------------
# SocialProfile
# ---------------------------------------------------------------------------

class TestSocialProfile:
    """SocialProfile field validation and backward-compatible aliases."""

    def test_create_with_new_field_names(self):
        p = SocialProfile(
            url="https://github.com/test",
            username="test",
            network_name="github",
            exists=True,
            image_url="https://img.example.com/a.png",
        )
        assert p.exists is True
        assert p.image_url == "https://img.example.com/a.png"

    def test_create_with_old_aliases(self):
        """Backward compat: constructors using old Spanish names must work."""
        p = SocialProfile(
            url="https://github.com/test",
            username="test",
            network_name="github",
            existe=True,
            imagen_url="https://img.example.com/a.png",
        )
        assert p.exists is True
        assert p.image_url == "https://img.example.com/a.png"

    def test_json_serialization_uses_new_names(self):
        p = SocialProfile(
            url="https://x.com/u", username="u", network_name="x", exists=True
        )
        d = p.model_dump(mode="json")
        assert "exists" in d
        assert "image_url" in d
        assert "existe" not in d
        assert "imagen_url" not in d

    def test_deserialize_from_old_json(self):
        raw = {
            "url": "https://x.com/u",
            "username": "u",
            "network_name": "x",
            "existe": True,
            "imagen_url": "https://old.png",
        }
        p = SocialProfile.model_validate(raw)
        assert p.exists is True
        assert p.image_url == "https://old.png"

    def test_defaults(self):
        p = SocialProfile(url="https://x.com/u", username="u", network_name="x")
        assert p.exists is False
        assert p.image_url is None
        assert p.bio is None
        assert p.metadata == {}

    def test_username_min_length(self):
        with pytest.raises(Exception):
            SocialProfile(url="https://x.com/", username="", network_name="x")

    def test_json_roundtrip(self):
        p = SocialProfile(
            url="https://github.com/test",
            username="test",
            network_name="github",
            exists=True,
            image_url="https://img.png",
            bio="Hello world",
            metadata={"source": "api"},
        )
        raw = p.model_dump(mode="json")
        p2 = SocialProfile.model_validate(raw)
        assert p2 == p


# ---------------------------------------------------------------------------
# PersonEntity
# ---------------------------------------------------------------------------

class TestPersonEntity:
    def test_aggregate_profiles(self):
        profiles = [
            SocialProfile(url="https://github.com/u", username="u", network_name="github", exists=True),
            SocialProfile(url="https://x.com/u", username="u", network_name="x", exists=False),
        ]
        person = PersonEntity(target="u", profiles=profiles)
        assert len(person.profiles) == 2
        confirmed = [p for p in person.profiles if p.exists]
        assert len(confirmed) == 1

    def test_empty_profiles(self):
        person = PersonEntity(target="nobody")
        assert person.profiles == []
        assert person.analysis is None


# ---------------------------------------------------------------------------
# AnalysisReport
# ---------------------------------------------------------------------------

class TestAnalysisReport:
    def test_create_report(self):
        report = AnalysisReport(
            summary="## 1. Test\nContent\n## 6. End",
            highlights=["Point 1", "Point 2"],
            confidence=0.75,
            model="deepseek-chat",
        )
        assert report.confidence == 0.75
        assert len(report.highlights) == 2
        assert report.generated_at is not None

    def test_confidence_bounds(self):
        with pytest.raises(Exception):
            AnalysisReport(summary="x", confidence=1.5)
        with pytest.raises(Exception):
            AnalysisReport(summary="x", confidence=-0.1)
