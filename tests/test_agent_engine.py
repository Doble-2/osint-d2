"""Tests for the agent engine."""

from __future__ import annotations

from core.services.agent_engine import AgentStep, AgentResult, _build_agent_system_prompt
from core.domain.language import Language
from core.domain.models import PersonEntity


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

class TestAgentSystemPrompt:
    def test_english_prompt(self):
        prompt = _build_agent_system_prompt(language=Language.ENGLISH, max_steps=10)
        assert "OSINT" in prompt
        assert "10" in prompt
        assert "generate_report" in prompt

    def test_spanish_prompt(self):
        prompt = _build_agent_system_prompt(language=Language.SPANISH, max_steps=5)
        assert "OSINT" in prompt
        assert "5" in prompt
        assert "Español" in prompt

    def test_max_steps_in_prompt(self):
        prompt = _build_agent_system_prompt(language=Language.ENGLISH, max_steps=25)
        assert "25" in prompt


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

class TestAgentStep:
    def test_step_with_tool(self):
        step = AgentStep(
            step_number=1,
            tool_name="scan_username",
            tool_args={"username": "torvalds"},
            tool_result='{"confirmed": 9}',
        )
        assert step.step_number == 1
        assert step.tool_name == "scan_username"

    def test_step_with_reasoning(self):
        step = AgentStep(
            step_number=2,
            reasoning="I should investigate the email next.",
        )
        assert step.reasoning is not None
        assert step.tool_name is None


class TestAgentResult:
    def test_result_finished(self):
        person = PersonEntity(target="test", profiles=[])
        result = AgentResult(
            person=person,
            steps=[AgentStep(step_number=1)],
            total_steps=1,
            finished_naturally=True,
        )
        assert result.finished_naturally
        assert result.total_steps == 1

    def test_result_not_finished(self):
        person = PersonEntity(target="test", profiles=[])
        result = AgentResult(
            person=person,
            steps=[],
            total_steps=0,
            finished_naturally=False,
        )
        assert not result.finished_naturally
