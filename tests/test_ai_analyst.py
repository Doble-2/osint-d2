"""Tests for AI analyst: heuristic analysis and helper functions."""

from __future__ import annotations

import pytest

from adapters.ai_analyst import _heuristic_analysis, _summary_has_six_sections
from core.domain.language import Language
from core.domain.models import PersonEntity, SocialProfile


# ---------------------------------------------------------------------------
# _summary_has_six_sections
# ---------------------------------------------------------------------------

class TestSummaryHasSixSections:
    def test_valid_summary(self):
        text = "## 1. Identity\nblah\n## 2. Geo\n## 3. Psych\n## 4. Tech\n## 5. Values\n## 6. OpSec"
        assert _summary_has_six_sections(summary=text, language=Language.ENGLISH) is True

    def test_missing_section_6(self):
        text = "## 1. Identity\nOnly one section"
        assert _summary_has_six_sections(summary=text, language=Language.ENGLISH) is False

    def test_empty_string(self):
        assert _summary_has_six_sections(summary="", language=Language.ENGLISH) is False

    def test_none_like(self):
        assert _summary_has_six_sections(summary="   ", language=Language.SPANISH) is False

    @pytest.mark.parametrize("language", list(Language))
    def test_all_languages_use_same_logic(self, language: Language):
        good = "## 1. Test\n## 6. End"
        assert _summary_has_six_sections(summary=good, language=language) is True


# ---------------------------------------------------------------------------
# _heuristic_analysis
# ---------------------------------------------------------------------------

def _make_person(confirmed: int = 1, unconfirmed: int = 1) -> PersonEntity:
    profiles = []
    for i in range(confirmed):
        profiles.append(SocialProfile(
            url=f"https://site{i}.com/u", username="u", network_name=f"site{i}", exists=True,
        ))
    for i in range(unconfirmed):
        profiles.append(SocialProfile(
            url=f"https://no{i}.com/u", username="u", network_name=f"no{i}", exists=False,
        ))
    return PersonEntity(target="testuser", profiles=profiles)


class TestHeuristicAnalysis:
    @pytest.mark.parametrize("language", list(Language))
    def test_all_languages_produce_valid_report(self, language: Language):
        person = _make_person(confirmed=2, unconfirmed=3)
        report = _heuristic_analysis(person=person, language=language, reason="test")

        assert report.model == "heuristic"
        assert report.confidence == 0.25
        assert len(report.highlights) >= 2
        assert "## 1." in report.summary
        assert "## 6." in report.summary

    def test_portuguese_no_breaches_does_not_crash(self):
        """Regression: Portuguese heuristic used to raise UnboundLocalError
        when no breach_lines were present because 'highlights' was only
        defined inside 'if breach_lines:'."""
        person = _make_person(confirmed=1, unconfirmed=0)
        report = _heuristic_analysis(person=person, language=Language.PORTUGUESE, reason="no_breaches")
        assert report.highlights is not None
        assert len(report.highlights) >= 2

    def test_zero_profiles(self):
        person = PersonEntity(target="ghost", profiles=[])
        report = _heuristic_analysis(person=person, language=Language.ENGLISH, reason="empty")
        assert "0 / 0" in report.summary or "0" in report.summary

    def test_reason_appears_in_summary(self):
        person = _make_person()
        report = _heuristic_analysis(person=person, language=Language.ENGLISH, reason="missing_api_key")
        assert "missing_api_key" in report.summary
