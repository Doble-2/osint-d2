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
from core.services.agent_tools import AGENT_TOOLS, execute_tool

logger = logging.getLogger(__name__)


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


# ---------------------------------------------------------------------------
# System prompt builder
# ---------------------------------------------------------------------------

def _build_agent_system_prompt(*, language: Language, max_steps: int) -> str:
    if language == Language.SPANISH:
        return (
            "Eres un investigador OSINT experto y Perfilador Criminalista. "
            "Tu objetivo es construir un perfil completo de la persona indicada.\n\n"
            "MÉTODO:\n"
            "1. Empieza con lo que sabes (username/email proporcionado)\n"
            "2. Usa las herramientas para recopilar evidencia de múltiples fuentes\n"
            "3. Analiza los resultados y decide qué investigar después\n"
            "4. PIVOTEA: si encuentras emails, usernames, aliases o websites nuevos en los resultados, investígalos\n"
            "5. Cuando tengas suficiente evidencia, llama generate_report con un análisis completo\n\n"
            "REGLAS:\n"
            f"- Máximo {max_steps} pasos. Prioriza las fuentes más ricas en datos.\n"
            "- No inventes datos. Solo reporta lo que las herramientas confirmen.\n"
            "- Si un scan falla o no encuentra nada, continúa con otras fuentes.\n"
            "- Busca patrones: mismo avatar en varias redes, misma bio, emails cruzados.\n"
            "- El reporte final debe seguir las 6 dimensiones: Identidad, Geo-temporal, "
            "Psicológico (OCEAN), Técnico/Profesional, Ideología, y Vectores de Ataque (OpSec).\n\n"
            "IDIOMA DE RESPUESTA: Español neutro."
        )

    return (
        "You are an expert OSINT investigator and Criminal Profiler. "
        "Your objective is to build a comprehensive profile of the target person.\n\n"
        "METHOD:\n"
        "1. Start with what you know (provided username/email)\n"
        "2. Use the tools to gather evidence from multiple sources\n"
        "3. Analyze results and decide what to investigate next\n"
        "4. PIVOT: if you find new emails, usernames, aliases, or websites in results, investigate them\n"
        "5. When you have enough evidence, call generate_report with a comprehensive analysis\n\n"
        "RULES:\n"
        f"- Maximum {max_steps} steps. Prioritize data-rich sources.\n"
        "- Do NOT fabricate data. Only report what the tools confirm.\n"
        "- If a scan fails or returns nothing, move on to other sources.\n"
        "- Look for patterns: same avatar across networks, same bio, cross-referenced emails.\n"
        "- The final report must cover 6 dimensions: Identity & Demographics, "
        "Geo-temporal Analysis, Psychological Profile (OCEAN), Technical/Professional, "
        "Ideology & Values, and Attack Surface (OpSec).\n\n"
        "RESPONSE LANGUAGE: English."
    )


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

    async def run(
        self,
        objective: str,
        *,
        language: Language = Language.ENGLISH,
        max_steps: int = 10,
        trust_anchors: list[str] | None = None,
    ) -> AgentResult:
        """Run the agent loop until it calls generate_report or exhausts steps."""

        client = AsyncOpenAI(
            api_key=self._settings.ai_api_key,
            base_url=self._settings.ai_base_url,
        )

        system_prompt = _build_agent_system_prompt(language=language, max_steps=max_steps)

        # Filter tools: remove breach_check if not enabled.
        tools = [t for t in AGENT_TOOLS if self._enable_breach_check or t["function"]["name"] != "breach_check"]

        # Build the user message with trust anchor context.
        user_content = f"Investigate: {objective}"
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

            if language == Language.SPANISH:
                trust_block = (
                    "\n\nFUENTES DE CONFIANZA (datos verificados por el usuario):\n"
                    + "\n".join(anchor_lines)
                    + "\n\nIMPORTANTE: Usa estas fuentes como verdad absoluta. "
                    "Si un perfil en otra red tiene un nombre/apellido diferente "
                    "al que se deduce de estas fuentes, ese perfil probablemente "
                    "pertenece a OTRA PERSONA. No confundas identidades."
                )
            else:
                trust_block = (
                    "\n\nTRUSTED SOURCES (user-verified data):\n"
                    + "\n".join(anchor_lines)
                    + "\n\nIMPORTANT: Use these as ground truth. "
                    "If a profile on another network has a different name/surname "
                    "than what these sources suggest, that profile likely belongs "
                    "to a DIFFERENT PERSON. Do NOT conflate identities."
                )
            user_content += trust_block

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        steps: list[AgentStep] = []
        report_data: dict[str, Any] | None = None

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
                        tc_step.tool_args = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        tc_step.tool_args = {"raw": tool_call.function.arguments}

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
                        "content": result_str,
                    })

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

                # If this is the last step and no report was generated,
                # the agent ran out of steps.

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

        # Build the result.
        target = objective.split()[-1] if objective else "unknown"
        person = PersonEntity(
            target=target,
            profiles=self._collected_profiles,
        )

        if report_data:
            # Parse highlights: handle both list and JSON-encoded string.
            raw_highlights = report_data.get("highlights", [])
            if isinstance(raw_highlights, str):
                try:
                    raw_highlights = json.loads(raw_highlights)
                except (json.JSONDecodeError, TypeError):
                    raw_highlights = [raw_highlights] if raw_highlights else []

            person.analysis = AnalysisReport(
                summary=report_data.get("summary", "Agent completed investigation."),
                highlights=raw_highlights if isinstance(raw_highlights, list) else [],
                confidence=min(1.0, max(0.0, float(report_data.get("confidence", 0.5)))),
                model=self._settings.ai_model,
                raw={"agent_steps": len(steps), "report_data": report_data},
            )

        return AgentResult(
            person=person,
            steps=steps,
            total_steps=len(steps),
            finished_naturally=report_data is not None,
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
                self._collected_profiles.append(SocialProfile(
                    url=p.get("url", ""),
                    username=p.get("username", "unknown"),
                    network_name=p.get("network", "unknown"),
                    exists=bool(p.get("exists", False)),
                    metadata=p,
                    bio=p.get("bio"),
                    image_url=p.get("avatar"),
                ))
            except Exception:
                continue
