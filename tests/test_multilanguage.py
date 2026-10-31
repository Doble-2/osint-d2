"""The agent and the graph must work the same way in every language."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from adapters.chain_builder import ChainBuilder
from adapters.radial_graph_renderer import RadialGraphRenderer
from core.domain.language import Language
from core.domain.models import AnalysisReport, PersonEntity
from core.services.agent_prompts import PROMPTS, build_objective, build_system_prompt

ALL_LANGUAGES = list(Language)
SPANISH_ONLY = ("CONCLUSIONES", "Objetivo", "SITIO WEB", "CONFIANZA GLOBAL")


def _steps():
    profiles = [{"network": "github", "username": "demo", "exists": True, "name": "Jane", "followers": 3}]
    return [
        SimpleNamespace(step_number=1, tool_name="scan_username", tool_args={"username": "demo"},
                        tool_result=json.dumps({"total_scanned": 4, "confirmed": 1, "profiles": profiles})),
        SimpleNamespace(step_number=2, tool_name="scan_phone", tool_args={"phone_number": "+15550100"},
                        tool_result=json.dumps({"carrier": "Demo", "whatsapp_active": True})),
    ]


def _person():
    report = AnalysisReport(summary="demo", highlights=["demo finding"], confidence=0.5, model="m")
    return PersonEntity(target="Jane Doe", profiles=[], analysis=report)


@pytest.mark.parametrize("language", ALL_LANGUAGES)
class TestAgentPrompts:
    def test_every_language_has_prompts(self, language):
        assert language in PROMPTS

    def test_system_prompt_keeps_the_rules(self, language):
        prompt = build_system_prompt(language=language, max_steps=7, sensitive_inferences=True)
        assert "{max_steps}" not in prompt
        assert "7" in prompt
        for token in ("generate_report", "BM25", "stylometric_score", "hamming_distance", "similarity_percentage", "OCEAN", "OpSec", "0.70"):
            assert token in prompt, token

    def test_objective_interpolates_everything(self, language):
        text = build_objective(
            language=language, target="Jane {x}", usernames=["demo"], emails=["a@b.co"], phones=[], trust_anchors=["github:demo"],
        )
        for value in ("Jane {x}", "demo", "a@b.co", "github:demo"):
            assert value in text
        assert "{target}" not in text and "{anchors}" not in text and "{phones}" not in text


def test_prompts_differ_by_language():
    prompts = {build_system_prompt(language=language, max_steps=5) for language in ALL_LANGUAGES}
    assert len(prompts) == len(ALL_LANGUAGES)


@pytest.mark.parametrize("language", ALL_LANGUAGES)
def test_graph_renders_every_language(language):
    chain = ChainBuilder.build_chain(_steps(), "Jane Doe", _person(), language=language)
    svg = RadialGraphRenderer.render_svg(chain, target="Jane Doe", confidence=0.5, language=language)
    assert "Jane Doe" in svg
    assert "{" not in svg.split("</defs>")[1]
    if language != Language.SPANISH:
        for text in SPANISH_ONLY:
            assert text not in svg, text


def test_graph_translates_field_labels():
    chain = ChainBuilder.build_chain(_steps(), "Jane Doe", _person(), language=Language.RUSSIAN)
    svg = RadialGraphRenderer.render_svg(chain, target="Jane Doe", confidence=0.5, language=Language.RUSSIAN)
    assert "Оператор" in svg
    assert "Да" in svg
    assert "Подписчики" in svg


def test_arabic_graph_has_no_letter_spacing():
    chain = ChainBuilder.build_chain(_steps(), "Jane Doe", _person(), language=Language.ARABIC)
    svg = RadialGraphRenderer.render_svg(chain, target="Jane Doe", confidence=0.5, language=Language.ARABIC)
    assert 'letter-spacing="1.6"' not in svg
