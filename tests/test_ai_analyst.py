"""Tests for AI analyst: heuristic analysis and helper functions."""

from __future__ import annotations

import json
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from adapters import ai_analyst
from adapters.ai_analyst import _heuristic_analysis, _summary_has_sections
from core.config import AppSettings
from core.domain.language import Language
from core.domain.models import PersonEntity, SocialProfile


# ---------------------------------------------------------------------------
# _summary_has_sections
# ---------------------------------------------------------------------------

class TestSummaryHasSections:
    @pytest.mark.parametrize("sections", [(1, 2, 4), (1, 2, 3, 4, 5, 6)])
    def test_valid_summary(self, sections):
        assert _summary_has_sections(summary=_summary(sections), expected_sections=sections) is True

    @pytest.mark.parametrize("summary", ["", "   ", "## 1. Identity\n## 6. OpSec"])
    def test_incomplete_summary(self, summary):
        assert _summary_has_sections(summary=summary, expected_sections=(1, 2, 3, 4, 5, 6)) is False

    @pytest.mark.parametrize("sections", [(1, 2, 4), (1, 2, 3, 4, 5, 6)])
    def test_rejects_each_missing_section(self, sections):
        for missing in sections:
            text = "\n".join(f"## {section}. Test" for section in sections if section != missing)
            assert _summary_has_sections(
                summary=text, expected_sections=sections,
            ) is False, f"Missing section {missing} was accepted"


def _summary(sections):
    return "\n".join(f"## {section}. Section\nObserved evidence." for section in sections)


def _reply(summary, *, highlights=None):
    content = json.dumps({
        "summary": summary,
        "highlights": ["An observed public profile."] if highlights is None else highlights,
        "confidence": 0.5,
    })
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


async def _analyze_replies(monkeypatch, *, replies, language, sensitive_inferences):
    snapshots = []

    async def create(**kwargs):
        snapshots.append([dict(message) for message in kwargs["messages"]])
        return replies[len(snapshots) - 1]

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(ai_analyst, "AsyncOpenAI", lambda **kwargs: client)
    monkeypatch.setattr(ai_analyst.asyncio, "sleep", AsyncMock())
    settings = AppSettings(
        _env_file=None, ai_api_key="test-key", ai_model="test-model", ai_max_retries=1,
        sensitive_inferences=sensitive_inferences,
    )
    report = await ai_analyst.analyze_person(
        person=PersonEntity(target="testuser"), language=language, settings=settings,
    )
    return report, snapshots


class TestReportSectionRetries:
    @pytest.mark.parametrize("language", list(Language))
    @pytest.mark.parametrize("sensitive_inferences, sections", [
        (False, (1, 2, 4)), (True, (1, 2, 3, 4, 5, 6)),
    ])
    async def test_complete_report_needs_no_retry(self, monkeypatch, language, sensitive_inferences, sections):
        summary = _summary(sections)
        report, snapshots = await _analyze_replies(
            monkeypatch, replies=[_reply(summary)], language=language, sensitive_inferences=sensitive_inferences,
        )
        assert len(snapshots) == 1
        assert report.model == "test-model"
        assert report.summary == summary

    @pytest.mark.parametrize("language", list(Language))
    @pytest.mark.parametrize("sensitive_inferences, sections", [
        (False, (1, 2, 4)), (True, (1, 2, 3, 4, 5, 6)),
    ])
    @pytest.mark.parametrize("problem", ["missing_sections", "template"])
    async def test_retry_uses_expected_sections(self, monkeypatch, language, sensitive_inferences, sections, problem):
        summary = _summary(sections)
        bad_reply = (
            _reply(_summary((sections[0], sections[-1])))
            if problem == "missing_sections" else _reply(summary, highlights=[])
        )
        report, snapshots = await _analyze_replies(
            monkeypatch, replies=[bad_reply, _reply(summary)], language=language,
            sensitive_inferences=sensitive_inferences,
        )
        assert len(snapshots) == 2
        correction = snapshots[1][-1]["content"]
        assert ", ".join(f"'## {section}.'" for section in sections) in correction
        assert {int(section) for section in re.findall(r"##\s*(\d+)\.", correction)} == set(sections)
        assert report.model == "test-model"
        assert report.summary == summary


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
