"""Tests for AgentEngine.run() with fully mocked LLM client (issue #32).

Covers:
- Single tool call → report flow
- Max steps respected
- Forced report generation when steps exhausted
- LLM error handling
- on_step callback invocations
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.config import AppSettings
from core.services.agent_engine import AgentEngine, AgentStep


def _make_settings() -> AppSettings:
    return AppSettings(
        ai_api_key="test-key-123",
        ai_base_url="https://fake.api.local",
        ai_model="test-model",
    )


def _tool_call(*, name: str, arguments: dict, call_id: str = "call_1"):
    """Create a mock tool call object."""
    tc = MagicMock()
    tc.function.name = name
    tc.function.arguments = json.dumps(arguments)
    tc.id = call_id
    return tc


def _assistant_message(*, tool_calls=None, content=None):
    """Create a mock assistant message."""
    msg = MagicMock()
    msg.tool_calls = tool_calls
    msg.content = content
    msg.model_dump.return_value = {
        "role": "assistant",
        "content": content,
        "tool_calls": [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
            }
            for tc in (tool_calls or [])
        ] or None,
    }
    return msg


def _chat_response(*, message):
    """Create a mock chat completion response."""
    choice = MagicMock()
    choice.message = message
    resp = MagicMock()
    resp.choices = [choice]
    return resp


# ---------------------------------------------------------------------------
# Single tool call → report
# ---------------------------------------------------------------------------

class TestSingleToolCallToReport:
    @pytest.mark.asyncio
    async def test_scan_then_report(self):
        """LLM calls scan_username, then generate_report → finished_naturally=True."""

        # Step 1: LLM wants to call scan_username
        scan_call = _tool_call(
            name="scan_username",
            arguments={"username": "testuser"},
            call_id="call_scan",
        )
        scan_msg = _assistant_message(tool_calls=[scan_call])
        scan_response = _chat_response(message=scan_msg)

        # Step 2: LLM calls generate_report
        report_call = _tool_call(
            name="generate_report",
            arguments={
                "summary": "## 1. Identity\nTest analysis",
                "highlights": ["Found on GitHub"],
                "confidence": 0.8,
            },
            call_id="call_report",
        )
        report_msg = _assistant_message(tool_calls=[report_call])
        report_response = _chat_response(message=report_msg)

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=[scan_response, report_response]
        )

        # Mock execute_tool to return scan results
        scan_result = json.dumps({
            "target": "testuser",
            "total_scanned": 1,
            "confirmed": 1,
            "profiles": [{"network": "github", "username": "testuser", "exists": True, "url": "https://github.com/testuser"}],
        })

        with patch("core.services.agent_engine.AsyncOpenAI", return_value=mock_client), \
             patch("core.services.agent_engine.execute_tool", AsyncMock(return_value=scan_result)):
            engine = AgentEngine(settings=_make_settings())
            result = await engine.run("investigate testuser", max_steps=5)

        assert result.finished_naturally is True
        assert result.total_steps >= 2


# ---------------------------------------------------------------------------
# Max steps respected
# ---------------------------------------------------------------------------

class TestMaxStepsRespected:
    @pytest.mark.asyncio
    async def test_stops_after_max_steps(self):
        """Engine should stop after max_steps even if LLM keeps calling tools."""

        # LLM always wants to call scan_username (never calls generate_report)
        scan_call = _tool_call(
            name="scan_username",
            arguments={"username": "user"},
            call_id="call_1",
        )
        scan_msg = _assistant_message(tool_calls=[scan_call])
        scan_response = _chat_response(message=scan_msg)

        # For forced report: LLM returns text instead of tool call
        text_msg = _assistant_message(content="Final analysis summary.")
        text_response = _chat_response(message=text_msg)

        mock_client = AsyncMock()
        # 3 scan responses + 1 forced report attempt
        mock_client.chat.completions.create = AsyncMock(
            side_effect=[scan_response, scan_response, scan_response, text_response]
        )

        scan_result = json.dumps({
            "target": "user",
            "profiles": [{"network": "github", "username": "user", "exists": True, "url": "https://github.com/user"}],
        })

        with patch("core.services.agent_engine.AsyncOpenAI", return_value=mock_client), \
             patch("core.services.agent_engine.execute_tool", AsyncMock(return_value=scan_result)):
            engine = AgentEngine(settings=_make_settings())
            result = await engine.run("investigate user", max_steps=3)

        assert result.total_steps <= 4  # 3 steps + possible forced report


# ---------------------------------------------------------------------------
# LLM error handling
# ---------------------------------------------------------------------------

class TestLLMErrorHandling:
    @pytest.mark.asyncio
    async def test_llm_error_breaks_loop(self):
        """If the LLM call raises, the loop should break with error recorded."""

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=Exception("API connection failed")
        )

        with patch("core.services.agent_engine.AsyncOpenAI", return_value=mock_client):
            engine = AgentEngine(settings=_make_settings())
            result = await engine.run("investigate user", max_steps=5)

        assert result.total_steps >= 1
        # The first step should have recorded the error
        error_step = result.steps[0]
        assert error_step.reasoning is not None
        assert "LLM error" in error_step.reasoning
        assert result.finished_naturally is False


# ---------------------------------------------------------------------------
# on_step callback
# ---------------------------------------------------------------------------

class TestOnStepCallbackInLoop:
    @pytest.mark.asyncio
    async def test_callback_called_for_each_step(self):
        """on_step should be called for every step in the loop."""
        captured_steps: list[AgentStep] = []

        # LLM sends text, then error (to end quickly)
        text_msg = _assistant_message(content="Thinking...")
        text_response = _chat_response(message=text_msg)

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=[text_response, Exception("done")]
        )

        with patch("core.services.agent_engine.AsyncOpenAI", return_value=mock_client):
            engine = AgentEngine(
                settings=_make_settings(),
                on_step=lambda s: captured_steps.append(s),
            )
            await engine.run("investigate user", max_steps=3)

        # At least 1 step should have triggered the callback
        assert len(captured_steps) >= 1


# ---------------------------------------------------------------------------
# Forced report generation
# ---------------------------------------------------------------------------

class TestForcedReport:
    @pytest.mark.asyncio
    async def test_forced_report_when_profiles_collected(self):
        """When max_steps exhausted with collected profiles, engine forces report."""

        # Step 1: LLM calls scan_username
        scan_call = _tool_call(
            name="scan_username",
            arguments={"username": "user"},
            call_id="call_1",
        )
        scan_msg = _assistant_message(tool_calls=[scan_call])
        scan_response = _chat_response(message=scan_msg)

        # Forced report: LLM calls generate_report
        report_call = _tool_call(
            name="generate_report",
            arguments={
                "summary": "Forced analysis",
                "highlights": ["Found"],
                "confidence": 0.5,
            },
            call_id="call_forced",
        )
        report_msg = _assistant_message(tool_calls=[report_call])
        forced_response = _chat_response(message=report_msg)

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=[scan_response, forced_response]
        )

        scan_result = json.dumps({
            "target": "user",
            "profiles": [{"network": "github", "username": "user", "exists": True, "url": "https://github.com/user"}],
        })

        with patch("core.services.agent_engine.AsyncOpenAI", return_value=mock_client), \
             patch("core.services.agent_engine.execute_tool", AsyncMock(return_value=scan_result)):
            engine = AgentEngine(settings=_make_settings())
            result = await engine.run("investigate user", max_steps=1)

        # Should have generated a report even though max_steps was 1
        assert result.person is not None
