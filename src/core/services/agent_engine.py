"""Autonomous OSINT agent powered by LLM function calling.

The engine implements a reasoning loop:
  1. Send context + tools to LLM
  2. LLM decides which tool to call (or generates the final report)
  3. Execute the tool, append result to conversation
  4. Repeat until ``generate_report`` is called or ``max_steps`` is reached
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from openai import AsyncOpenAI

from core.config import AppSettings
from core.domain.language import Language
from core.domain.models import AnalysisReport, PersonEntity, SocialProfile
from adapters.vector_store import VectorStore
from core.services.agent_prompts import PROMPTS, build_system_prompt
from core.services.agent_tools import AGENT_TOOLS, execute_tool
from core.services.report_scope import strip_sensitive_sections

logger = logging.getLogger(__name__)

# Kept for callers and tests that build the prompt through this module.
_build_agent_system_prompt = build_system_prompt


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class AgentStep:
    """One step in the agent's reasoning process."""

    step_number: int
    tool_name: str | None = None
    tool_args: dict[str, Any] = field(default_factory=dict)
    tool_result: str | None = None
    reasoning: str | None = None


@dataclass
class AgentResult:
    """Final output of the agent."""

    person: PersonEntity
    steps: list[AgentStep] = field(default_factory=list)
    total_steps: int = 0
    finished_naturally: bool = False  # True if agent called generate_report


_MAX_SUMMARY_CHARS = 20_000
# Tool results come from third parties: they must not fill the model's context.
_MAX_TOOL_RESULT_CHARS = 30_000
_MAX_TOOL_CONTEXT_CHARS = 200_000
_UNTRUSTED_TAG = "untrusted_data"


def _untrusted_message(result: str, budget: int) -> str:
    """Wrap a tool result so a hostile page cannot close the tag and pose as instructions."""
    if budget <= 0:
        return '{"error": "Evidence budget used up: call generate_report now."}'
    body = result[:min(_MAX_TOOL_RESULT_CHARS, budget)].replace(f"</{_UNTRUSTED_TAG}", f"<\\/{_UNTRUSTED_TAG}")
    if len(result) > min(_MAX_TOOL_RESULT_CHARS, budget):
        body += " [truncated]"
    return f"<{_UNTRUSTED_TAG}>\n{body}\n</{_UNTRUSTED_TAG}>"


def _parse_confidence(value: Any) -> float:
    """Clamp the LLM-supplied confidence to [0, 1]; models may return non-numbers."""
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.5
    if confidence != confidence:  # NaN
        return 0.5
    return min(1.0, max(0.0, confidence))


# ---------------------------------------------------------------------------
# Agent Engine
# ---------------------------------------------------------------------------

class AgentEngine:
    """Autonomous OSINT agent using LLM function calling."""

    def __init__(
        self,
        *,
        settings: AppSettings,
        enable_breach_check: bool = False,
        on_step: Callable[[AgentStep], None] | None = None,
    ) -> None:
        self._settings = settings
        self._enable_breach_check = enable_breach_check
        self._on_step = on_step
        self._collected_profiles: list[SocialProfile] = []
        self._profile_index: dict[tuple[str, str], int] = {}
        self._vector_store = VectorStore()
        # Identificador real del objetivo, fijado por el llamador (web/CLI).
        self._explicit_target: str | None = None

    async def run(
        self,
        objective: str,
        *,
        language: Language = Language.ENGLISH,
        max_steps: int = 10,
        trust_anchors: list[str] | None = None,
        target: str | None = None,
    ) -> AgentResult:
        """Run the agent loop until it calls generate_report or exhausts steps.

        Parameters
        ----------
        target:
            The identifier being investigated. When provided it becomes the
            PersonEntity target verbatim, instead of guessing from the objective.
        """
        if target:
            self._explicit_target = target

        # Determine effective API key and base URL (Ollama doesn't require real key)
        is_ollama = self._settings.ai_provider.lower() == "ollama"
        api_key_str = ""
        if self._settings.ai_api_key:
            api_key_str = self._settings.ai_api_key.get_secret_value()
        elif is_ollama:
            api_key_str = "ollama"
        else:
            raise ValueError(
                "OSINT_D2_AI_API_KEY is not configured. "
                "Set it via environment variable, .env file, or set OSINT_D2_AI_PROVIDER=ollama"
            )

        client = AsyncOpenAI(
            api_key=api_key_str,
            base_url=self._settings.ai_base_url,
            max_retries=self._settings.ai_max_retries,
        )

        sensitive_inferences = self._settings.sensitive_inferences
        system_prompt = build_system_prompt(
            language=language, max_steps=max_steps, sensitive_inferences=sensitive_inferences,
        )
        prompts = PROMPTS[language]

        # Filter tools: remove breach_check if not enabled.
        tools = [t for t in AGENT_TOOLS if self._enable_breach_check or t["function"]["name"] != "breach_check"]

        # Build the user message with trust anchor context.
        user_content = prompts.investigate.replace("{objective}", objective)
        if trust_anchors:
            anchor_lines = []
            for anchor_str in trust_anchors:
                parts = anchor_str.split(":", 1)
                if len(parts) == 2:
                    net, user = parts
                    if net.lower() == "email":
                        anchor_lines.append(f"- VERIFIED EMAIL: {user}")
                    else:
                        anchor_lines.append(f"- VERIFIED {net.upper()} account: @{user}")

            trust_block = "\n\n" + prompts.trusted_header + "\n" + "\n".join(anchor_lines) + "\n\n" + prompts.trusted_rule
            user_content += trust_block

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        steps: list[AgentStep] = []
        report_data: dict[str, Any] | None = None
        tool_budget = _MAX_TOOL_CONTEXT_CHARS

        for step_num in range(1, max_steps + 1):
            step = AgentStep(step_number=step_num)

            try:
                response = await client.chat.completions.create(
                    model=self._settings.ai_model,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                    timeout=self._settings.ai_timeout_seconds,
                )
            except Exception as exc:
                logger.error("Agent LLM call failed at step %d: %s", step_num, exc)
                step.reasoning = f"LLM error: {exc}"
                steps.append(step)
                if self._on_step:
                    self._on_step(step)
                break

            choice = response.choices[0]
            assistant_message = choice.message

            # If the LLM wants to call tools
            if assistant_message.tool_calls:
                # Add assistant message (with tool_calls) to history.
                messages.append(assistant_message.model_dump())

                for tool_call in assistant_message.tool_calls:
                    tc_step = AgentStep(step_number=step_num)
                    tc_step.tool_name = tool_call.function.name

                    try:
                        parsed_args = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        parsed_args = None
                    # Models can send valid JSON that isn't an object.
                    tc_step.tool_args = parsed_args if isinstance(parsed_args, dict) else {"raw": tool_call.function.arguments}

                    # Check if agent is done.
                    if tool_call.function.name == "generate_report":
                        report_data = tc_step.tool_args
                        tc_step.tool_result = '{"status": "report_generated"}'
                        steps.append(tc_step)
                        if self._on_step:
                            self._on_step(tc_step)

                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": tc_step.tool_result,
                        })
                        break

                    # Execute the tool.
                    try:
                        result_str = await execute_tool(
                            tool_call.function.name,
                            tc_step.tool_args,
                            settings=self._settings,
                            enable_breach_check=self._enable_breach_check,
                            vector_store=self._vector_store,
                        )
                    except Exception as exc:
                        logger.warning("Tool %s failed: %s", tool_call.function.name, exc)
                        result_str = json.dumps({"error": str(exc)})

                    tc_step.tool_result = result_str
                    steps.append(tc_step)
                    if self._on_step:
                        self._on_step(tc_step)

                    # Collect profiles from results.
                    self._collect_profiles_from_result(result_str)

                    # Add tool result to conversation.
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": _untrusted_message(result_str, tool_budget),
                    })
                    tool_budget -= min(len(result_str), _MAX_TOOL_RESULT_CHARS)

                if report_data is not None:
                    break

            else:
                # LLM responded with text (reasoning or final answer without tools).
                content = assistant_message.content or ""
                step.reasoning = content
                steps.append(step)
                if self._on_step:
                    self._on_step(step)

                messages.append({"role": "assistant", "content": content})
                # Repeating the same conversation would pay for the same answer.
                messages.append({"role": "user", "content": "Continue: call a tool, or call generate_report if you are done."})

        finished_naturally = report_data is not None

        # If the agent ran out of steps without generating a report,
        # force one final LLM call to produce the report.
        if report_data is None and self._collected_profiles:
            logger.info("Agent exhausted %d steps; forcing final report.", max_steps)
            force_msg = (
                "You have run out of investigation steps. You MUST now call "
                "generate_report immediately with a comprehensive analysis "
                "based on ALL the evidence gathered so far."
            )
            messages.append({"role": "user", "content": force_msg})

            # Only offer generate_report as a tool.
            report_tool = [t for t in AGENT_TOOLS if t["function"]["name"] == "generate_report"]

            try:
                response = await client.chat.completions.create(
                    model=self._settings.ai_model,
                    messages=messages,
                    tools=report_tool,
                    tool_choice={"type": "function", "function": {"name": "generate_report"}},
                    timeout=self._settings.ai_timeout_seconds,
                )
                choice = response.choices[0]
                if choice.message.tool_calls:
                    tc = choice.message.tool_calls[0]
                    try:
                        report_data = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        pass
                    force_step = AgentStep(
                        step_number=len(steps) + 1,
                        tool_name="generate_report",
                        tool_args=report_data or {},
                        tool_result='{"status": "report_generated"}',
                    )
                    steps.append(force_step)
                    if self._on_step:
                        self._on_step(force_step)
                elif choice.message.content:
                    # Some providers don't honor tool_choice; try to
                    # extract a report from the text response.
                    report_data = {
                        "summary": choice.message.content,
                        "highlights": [],
                        "confidence": 0.5,
                    }
            except Exception as exc:
                logger.warning("Forced report generation failed: %s", exc)

        # Build the result. The target must be the identifier the caller supplied,
        # never derived from the free-text objective: splitting the objective's
        # last word produced garbage like "qué." for objectives ending in a
        # question ("...y explica por qué.").
        target = self._explicit_target or (
            objective.split()[-1] if objective else "unknown"
        )
        person = PersonEntity(
            target=target,
            profiles=self._collected_profiles,
        )

        if report_data and isinstance(report_data, dict):
            # In place: the step history and analysis.raw hold this same dict.
            if not sensitive_inferences and isinstance(report_data.get("summary"), str):
                report_data["summary"] = strip_sensitive_sections(report_data["summary"])

            # Parse highlights: handle both list and JSON-encoded string.
            raw_highlights = report_data.get("highlights", [])
            if isinstance(raw_highlights, str):
                try:
                    raw_highlights = json.loads(raw_highlights)
                except (json.JSONDecodeError, TypeError):
                    raw_highlights = [raw_highlights] if raw_highlights else []

            person.analysis = AnalysisReport(
                # Models can exceed the report's size limit; keep what fits.
                summary=str(report_data.get("summary") or "Agent completed investigation.")[:_MAX_SUMMARY_CHARS],
                highlights=[str(h) for h in raw_highlights] if isinstance(raw_highlights, list) else [],
                confidence=_parse_confidence(report_data.get("confidence")),
                model=self._settings.ai_model,
                raw={"agent_steps": len(steps), "report_data": report_data},
            )

        return AgentResult(
            person=person,
            steps=steps,
            total_steps=len(steps),
            finished_naturally=finished_naturally,
        )

    def _collect_profiles_from_result(self, result_json: str) -> None:
        """Extract SocialProfile-like entries from tool results."""
        try:
            data = json.loads(result_json)
        except json.JSONDecodeError:
            return

        profiles_raw = data.get("profiles") or data.get("results") or []
        for p in profiles_raw:
            if not isinstance(p, dict):
                continue
            try:
                prof = SocialProfile(
                    url=p.get("url", ""),
                    username=p.get("username", "unknown"),
                    network_name=p.get("network", "unknown"),
                    exists=bool(p.get("exists", False)),
                    metadata=p,
                    bio=p.get("bio"),
                    image_url=p.get("avatar"),
                )
                # Pivots rescan the same accounts: keep one entry per account.
                key = (prof.network_name.lower(), prof.username.lower())
                known = self._profile_index.get(key)
                if known is not None:
                    if prof.exists and not self._collected_profiles[known].exists:
                        self._collected_profiles[known] = prof
                    else:
                        continue
                else:
                    self._profile_index[key] = len(self._collected_profiles)
                    self._collected_profiles.append(prof)

                # Index into vector store if exists and has text
                if prof.exists:
                    bio = p.get("bio") or ""
                    title = p.get("title") or ""
                    desc = p.get("description") or ""
                    combined = f"{title} {desc} {bio}".strip()
                    if combined:
                        self._vector_store.add_document(
                            doc_id=f"{prof.network_name}:{prof.username}",
                            source=prof.network_name,
                            text=combined,
                            metadata={"url": prof.url, "username": prof.username},
                        )
            except Exception as exc:
                logger.debug("Skipping malformed profile from tool result: %s", exc)
