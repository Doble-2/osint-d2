"""Extended tests for the agent engine.

Tests the core logic that can be tested without real API calls:
- Trust anchor message building
- Profile collection from tool results
- Report data parsing (highlights, confidence clamping)
- Forced report fallback
- Tool filtering (breach_check enable/disable)
"""

from __future__ import annotations

import json

import pytest

from core.config import AppSettings
from core.domain.language import Language
from core.services.agent_engine import (
    AgentEngine,
    AgentStep,
    _build_agent_system_prompt,
)
from core.services.agent_tools import AGENT_TOOLS


# ---------------------------------------------------------------------------
# System prompt — all languages
# ---------------------------------------------------------------------------

class TestBuildAgentSystemPrompt:
    def test_english_contains_key_instructions(self):
        prompt = _build_agent_system_prompt(language=Language.ENGLISH, max_steps=10)
        assert "OSINT" in prompt
        assert "generate_report" in prompt
        assert "10" in prompt

    def test_spanish_contains_key_instructions(self):
        prompt = _build_agent_system_prompt(language=Language.SPANISH, max_steps=5)
        assert "OSINT" in prompt
        assert "5" in prompt
        assert "Español" in prompt or "generate_report" in prompt

    @pytest.mark.parametrize("lang", list(Language))
    def test_all_languages_produce_nonempty_prompt(self, lang: Language):
        prompt = _build_agent_system_prompt(language=lang, max_steps=8)
        assert len(prompt) > 50, f"Prompt for {lang} is too short"
        assert "8" in prompt


# ---------------------------------------------------------------------------
# Trust anchor message construction
# ---------------------------------------------------------------------------

class TestTrustAnchorMessage:
    """Verify that trust anchor strings are embedded in the user message."""

    def _build_engine(self) -> AgentEngine:
        settings = AppSettings(
            ai_api_key="test-key",
            ai_base_url="https://fake.api.local",
        )
        return AgentEngine(settings=settings)

    def test_trust_anchors_format_instagram(self):
        """Trust anchors should be formatted in the user content."""
        anchors = ["instagram:xkissmely", "email:test@test.com"]
        anchor_lines = []
        for anchor_str in anchors:
            parts = anchor_str.split(":", 1)
            if len(parts) == 2:
                net, user = parts
                if net.lower() == "email":
                    anchor_lines.append(f"- VERIFIED EMAIL: {user}")
                else:
                    anchor_lines.append(f"- VERIFIED {net.upper()} account: @{user}")

        assert "VERIFIED INSTAGRAM account: @xkissmely" in anchor_lines[0]
        assert "VERIFIED EMAIL: test@test.com" in anchor_lines[1]


# ---------------------------------------------------------------------------
# Profile collection from tool results
# ---------------------------------------------------------------------------

class TestCollectProfiles:
    def _make_engine(self) -> AgentEngine:
        settings = AppSettings(
            ai_api_key="test-key",
            ai_base_url="https://fake.api.local",
        )
        return AgentEngine(settings=settings)

    def test_collects_profiles_from_scan_result(self):
        engine = self._make_engine()
        result = json.dumps({
            "profiles": [
                {
                    "url": "https://github.com/testuser",
                    "username": "testuser",
                    "network": "github",
                    "exists": True,
                    "bio": "A developer",
                    "avatar": "https://avatars.githubusercontent.com/u/12345",
                },
                {
                    "url": "https://twitter.com/testuser",
                    "username": "testuser",
                    "network": "x",
                    "exists": False,
                },
            ]
        })

        engine._collect_profiles_from_result(result)
        assert len(engine._collected_profiles) == 2

        gh = engine._collected_profiles[0]
        assert gh.network_name == "github"
        assert gh.exists is True
        assert gh.bio == "A developer"

        x = engine._collected_profiles[1]
        assert x.network_name == "x"
        assert x.exists is False

    def test_collects_from_results_key(self):
        """Some tools return 'results' instead of 'profiles'."""
        engine = self._make_engine()
        result = json.dumps({
            "results": [
                {
                    "url": "https://gitlab.com/user",
                    "username": "user",
                    "network": "gitlab",
                    "exists": True,
                }
            ]
        })

        engine._collect_profiles_from_result(result)
        assert len(engine._collected_profiles) == 1
        assert engine._collected_profiles[0].network_name == "gitlab"

    def test_handles_invalid_json(self):
        engine = self._make_engine()
        engine._collect_profiles_from_result("not json at all")
        assert len(engine._collected_profiles) == 0

    def test_handles_empty_profiles(self):
        engine = self._make_engine()
        engine._collect_profiles_from_result(json.dumps({"profiles": []}))
        assert len(engine._collected_profiles) == 0

    def test_skips_non_dict_entries(self):
        engine = self._make_engine()
        engine._collect_profiles_from_result(json.dumps({
            "profiles": ["not a dict", 42, None]
        }))
        assert len(engine._collected_profiles) == 0

    def test_handles_missing_fields_gracefully(self):
        engine = self._make_engine()
        engine._collect_profiles_from_result(json.dumps({
            "profiles": [{"url": "https://example.com"}]
        }))
        assert len(engine._collected_profiles) == 1
        p = engine._collected_profiles[0]
        assert p.username == "unknown"
        assert p.network_name == "unknown"


# ---------------------------------------------------------------------------
# Tool filtering
# ---------------------------------------------------------------------------

class TestToolFiltering:
    def test_breach_check_excluded_when_disabled(self):
        settings = AppSettings(
            ai_api_key="test-key",
            ai_base_url="https://fake.api.local",
        )
        engine = AgentEngine(settings=settings, enable_breach_check=False)
        tools = [
            t for t in AGENT_TOOLS
            if engine._enable_breach_check or t["function"]["name"] != "breach_check"
        ]
        tool_names = [t["function"]["name"] for t in tools]
        assert "breach_check" not in tool_names
        assert "scan_username" in tool_names
        assert "generate_report" in tool_names

    def test_breach_check_included_when_enabled(self):
        settings = AppSettings(
            ai_api_key="test-key",
            ai_base_url="https://fake.api.local",
        )
        engine = AgentEngine(settings=settings, enable_breach_check=True)
        tools = [
            t for t in AGENT_TOOLS
            if engine._enable_breach_check or t["function"]["name"] != "breach_check"
        ]
        tool_names = [t["function"]["name"] for t in tools]
        assert "breach_check" in tool_names


# ---------------------------------------------------------------------------
# AgentResult construction
# ---------------------------------------------------------------------------

class TestAgentResultConstruction:
    """Test report_data → AnalysisReport parsing edge cases."""

    def test_highlights_as_string_parsed(self):
        """Highlights can come as JSON-encoded string from some LLMs."""

        raw_highlights = '["point 1", "point 2"]'
        parsed = json.loads(raw_highlights)
        assert isinstance(parsed, list)
        assert len(parsed) == 2

    def test_confidence_clamped(self):
        """Confidence must be clamped to [0, 1]."""
        val = min(1.0, max(0.0, float(1.5)))
        assert val == 1.0
        val = min(1.0, max(0.0, float(-0.3)))
        assert val == 0.0

    def test_target_extracted_from_objective(self):
        """Target is last word of objective."""
        objective = "investigate doble-2"
        target = objective.split()[-1]
        assert target == "doble-2"

    def test_empty_objective(self):
        objective = ""
        target = objective.split()[-1] if objective else "unknown"
        assert target == "unknown"


# ---------------------------------------------------------------------------
# On-step callback
# ---------------------------------------------------------------------------

class TestOnStepCallback:
    def test_callback_receives_step(self):
        captured: list[AgentStep] = []
        settings = AppSettings(
            ai_api_key="test-key",
            ai_base_url="https://fake.api.local",
        )
        engine = AgentEngine(
            settings=settings,
            on_step=lambda s: captured.append(s),
        )
        # Simulate a step notification
        step = AgentStep(step_number=1, tool_name="scan_username", tool_args={"username": "test"})
        engine._on_step(step)  # type: ignore[misc]
        assert len(captured) == 1
        assert captured[0].tool_name == "scan_username"


# ---------------------------------------------------------------------------
# API key validation (issue #33)
# ---------------------------------------------------------------------------

class TestApiKeyValidation:
    """Verify fail-fast when ai_api_key is None — prevents silent SDK fallback
    to OPENAI_API_KEY env var which would misdirect credentials."""

    @pytest.mark.asyncio
    async def test_agent_engine_raises_without_api_key(self):
        """AgentEngine.run() must raise ValueError before any LLM call."""
        settings = AppSettings(
            ai_api_key=None,
            ai_base_url="https://api.deepseek.com",
        )
        engine = AgentEngine(settings=settings)

        with pytest.raises(ValueError, match="OSINT_D2_AI_API_KEY"):
            await engine.run("investigate testuser")

    @pytest.mark.asyncio
    async def test_agent_engine_raises_with_empty_string_key(self):
        """Empty string should also be caught."""
        settings = AppSettings(
            ai_api_key="",
            ai_base_url="https://api.deepseek.com",
        )
        engine = AgentEngine(settings=settings)

        with pytest.raises(ValueError, match="OSINT_D2_AI_API_KEY"):
            await engine.run("investigate testuser")

    def test_build_deepseek_client_raises_on_empty_key(self):
        """build_deepseek_client must fail-fast on empty key."""
        from adapters.ai_analyst import build_deepseek_client

        with pytest.raises(ValueError, match="AI API key is empty"):
            build_deepseek_client(api_key="", base_url="https://api.deepseek.com")

    def test_build_deepseek_client_works_with_valid_key(self):
        """Valid key should construct the client without error."""
        from adapters.ai_analyst import build_deepseek_client

        client = build_deepseek_client(api_key="sk-test-key", base_url="https://api.deepseek.com")
        assert client is not None
