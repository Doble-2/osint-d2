"""`agent`: autonomous investigations."""

from __future__ import annotations

import asyncio
import json
import sys

import typer
from rich.markup import escape
from rich.panel import Panel

from cli.ui_components import build_analysis_panel
from core.config import AppSettings
from core.domain.language import Language
from cli.app import app
from cli.shared import (
    SENSITIVE_INFERENCES_OPTION, apply_sensitive_inferences,
    AI_PROVIDER_HELP, apply_proxy_overrides, configure_ai_for_run,
    err_console, out_console, resolve_language, validate_ai_options, validate_trust,
)
from cli.output import handle_exports


@app.command(help="Autonomous OSINT investigation powered by agentic AI.")
def agent(
    objective: str = typer.Argument(
        ...,
        help="Investigation target or free-form objective (e.g. 'johndoe', 'user@example.com').",
    ),
    sensitive_inferences: bool = SENSITIVE_INFERENCES_OPTION,
    ai_provider: str | None = typer.Option(
        None,
        "--ai-provider",
        help=AI_PROVIDER_HELP,
        show_default=False,
    ),
    ai_key: str | None = typer.Option(
        None,
        "--ai-key",
        help="AI API key (optional). Prefer `osint-d2 doctor setup-ai`.",
        show_default=False,
    ),
    ai_save: bool = typer.Option(
        False,
        "--ai-save/--no-ai-save",
        help="Persist provider configuration for next runs.",
    ),
    max_steps: int = typer.Option(
        10,
        "--max-steps",
        min=1,
        max=50,
        help="Maximum reasoning steps before the agent must conclude.",
    ),
    language: Language | None = typer.Option(
        None,
        "--language",
        "-l",
        help="Output language: en|es|pt|ar|ru.",
    ),
    breach_check: bool = typer.Option(
        False,
        "--breach-check/--no-breach-check",
        help="Allow the agent to query the official HaveIBeenPwned API. Requires OSINT_D2_HIBP_API_KEY.",
    ),
    proxy: str | None = typer.Option(
        None,
        "--proxy",
        help="Override proxy mode: residential, datacenter.",
        show_default=False,
    ),
    no_proxy: bool = typer.Option(
        False,
        "--no-proxy",
        help="Disable proxy for this run.",
    ),
    proxy_country: str | None = typer.Option(
        None,
        "--proxy-country",
        help="2-letter country code for geo-targeted proxy.",
        show_default=False,
    ),
    export_json: bool = typer.Option(
        False,
        "--export-json/--no-export-json",
        help="Export the investigation as JSON in reports/.",
    ),
    export_pdf: bool = typer.Option(
        False,
        "--export-pdf/--no-export-pdf",
        help="Export a PDF/HTML dossier.",
    ),
    export_canvas: bool = typer.Option(
        False,
        "--export-canvas/--no-export-canvas",
        help="Export an interactive Obsidian Canvas (.canvas) entity graph.",
    ),
    export_html_graph: bool = typer.Option(
        False,
        "--export-html-graph/--no-export-html-graph",
        help="Export a standalone dark-themed interactive HTML graph.",
    ),
    trust: list[str] | None = typer.Option(
        None,
        "--trust",
        help="Known-good account (repeatable). Format: network:username or email:address, e.g. github:johndoe.",
        show_default=False,
    ),
) -> None:
    trust_anchors = validate_trust(trust)
    apply_sensitive_inferences(sensitive_inferences)
    validate_ai_options(analysis=True, ai_provider=ai_provider, ai_key=ai_key)
    language = resolve_language(language)
    settings = apply_proxy_overrides(
        AppSettings(), proxy=proxy, no_proxy=no_proxy, proxy_country=proxy_country,
    )
    if ai_provider:
        settings = configure_ai_for_run(
            settings=settings,
            ai_provider=ai_provider,
            ai_key=ai_key,
            ai_save=ai_save,
            interactive=sys.stdin.isatty() and sys.stdout.isatty(),
            console=out_console,
        )

    if not settings.ai_api_key and settings.ai_provider.lower() != "ollama":
        err_console.print(
            "[red]Error:[/red] Agent mode needs an AI provider key. "
            "Run [bold]osint-d2 doctor setup-ai[/bold], set OSINT_D2_AI_API_KEY, or use Ollama.",
        )
        raise typer.Exit(1)
    if breach_check and not settings.hibp_api_key:
        raise typer.BadParameter("--breach-check requires a HaveIBeenPwned API key in OSINT_D2_HIBP_API_KEY.")

    asyncio.run(
        agent_async(
            settings=settings,
            objective=objective,
            max_steps=max_steps,
            language=language,
            breach_check=breach_check,
            export_json=export_json,
            export_pdf=export_pdf,
            export_canvas=export_canvas,
            export_html=export_html_graph,
            trust_anchors=trust_anchors,
        )
    )


async def agent_async(
    *,
    settings: AppSettings,
    objective: str,
    max_steps: int,
    language: Language,
    breach_check: bool,
    export_json: bool,
    export_pdf: bool,
    export_canvas: bool = False,
    export_html: bool = False,
    trust_anchors: list[str],
) -> None:
    from core.services.agent_engine import AgentEngine, AgentStep

    console = out_console
    console.print(
        Panel(
            f"Objective: [yellow]{escape(objective)}[/yellow]\n"
            f"Max steps: [green]{max_steps}[/green]  Model: [green]{escape(settings.ai_model)}[/green]",
            title="OSINT-D2 Agent",
            border_style="bright_cyan",
            expand=False,
        )
    )

    def on_step(step: AgentStep) -> None:
        if step.tool_name:
            if step.tool_name == "generate_report":
                # Don't dump the full summary; it's shown in the panel after.
                confidence = step.tool_args.get("confidence", "?")
                n_highlights = 0
                raw_hl = step.tool_args.get("highlights", "")
                if isinstance(raw_hl, list):
                    n_highlights = len(raw_hl)
                elif isinstance(raw_hl, str):
                    try:
                        n_highlights = len(json.loads(raw_hl))
                    except Exception:
                        n_highlights = raw_hl.count("',") + (1 if raw_hl.strip() else 0)
                console.print(
                    f"  📋 [bold]Step {step.step_number}/{max_steps}:[/bold] "
                    f"[cyan]generate_report[/cyan]"
                    f"(confidence={escape(str(confidence))}, highlights={n_highlights})"
                )
            else:
                args_str = ", ".join(f'{k}="{v}"' for k, v in step.tool_args.items())
                console.print(
                    f"  🔍 [bold]Step {step.step_number}/{max_steps}:[/bold] "
                    f"[cyan]{escape(str(step.tool_name))}[/cyan]({escape(args_str)})"
                )
                if step.tool_result:
                    try:
                        data = json.loads(step.tool_result)
                        confirmed = data.get("confirmed", "?")
                        total = data.get("total_scanned", "?")
                        console.print(
                            f"     → [green]{confirmed}[/green] confirmed / {total} scanned"
                        )
                    except Exception:
                        pass
        elif step.reasoning:
            console.print(
                f"\n  🧠 [bold]Step {step.step_number}/{max_steps}:[/bold] [dim]Reasoning...[/dim]"
            )
            # Show first 200 chars of reasoning.
            preview = step.reasoning[:200].replace("\n", " ")
            console.print(f"     [italic dim]{escape(preview)}[/italic dim]\n")

    engine = AgentEngine(
        settings=settings,
        enable_breach_check=breach_check,
        on_step=on_step,
    )

    with console.status("[bold green]Agent is thinking...", spinner="dots"):
        result = await engine.run(
            objective,
            language=language,
            max_steps=max_steps,
            trust_anchors=trust_anchors,
        )

    console.print()
    person = result.person

    # ── Trust anchor filtering ──
    if trust_anchors:
        from core.services.trust_anchor import (
            TrustAnchor, build_reference_from_profiles, filter_profiles_by_trust,
        )
        anchors = [TrustAnchor.parse(a) for a in trust_anchors]
        ref = build_reference_from_profiles(person.profiles, anchors)
        if not ref.is_empty():
            before_count = sum(1 for p in person.profiles if p.exists)
            filter_profiles_by_trust(person.profiles, ref, remove=True)
            after_count = sum(
                1 for p in person.profiles
                if p.exists and not (
                    isinstance(p.metadata, dict) and p.metadata.get("trust_discarded")
                )
            )
            discarded = before_count - after_count
            if discarded:
                console.print(
                    f"  [yellow]🛡️ Trust anchors discarded {discarded} "
                    f"false positive(s)[/yellow]\n"
                )

    if result.finished_naturally:
        console.print(
            f"  [bold green]✓[/bold green] Agent concluded in "
            f"[bold]{result.total_steps}[/bold] steps.\n"
        )
    elif result.person.analysis:
        console.print(
            f"  [bold yellow]⚠[/bold yellow] Agent ran out of steps; the report covers "
            f"what it found in {result.total_steps} step(s).\n"
        )
    else:
        console.print(
            f"  [bold yellow]⚠[/bold yellow] Agent finished without a report "
            f"after {result.total_steps} step(s).\n"
        )

    # Show analysis first — it's the main deliverable in agent mode.
    if person.analysis:
        panel = build_analysis_panel(person.analysis)
        console.print(panel)

    # Show only confirmed profiles (the full table goes into the PDF).
    confirmed = [p for p in person.profiles if p.exists]
    if confirmed:
        from rich.table import Table as RichTable

        # Deduplicate by (network, username).
        seen: set[tuple[str, str]] = set()
        unique_confirmed: list = []
        for p in confirmed:
            key = (p.network_name, p.username)
            if key not in seen:
                seen.add(key)
                unique_confirmed.append(p)

        tbl = RichTable(
            title="Confirmed Profiles",
            title_style="bold bright_cyan",
            border_style="dim",
            show_lines=False,
        )
        tbl.add_column("Network", style="bold")
        tbl.add_column("Username")
        tbl.add_column("URL", style="dim")
        for p in unique_confirmed:
            tbl.add_row(
                p.network_name,
                p.username,
                str(p.url)[:72] + ("…" if len(str(p.url)) > 72 else ""),
            )
        console.print()
        console.print(tbl)
        console.print(
            f"\n  [dim]{len(unique_confirmed)} confirmed / "
            f"{len(person.profiles)} total scanned "
            f"(full table in PDF)[/dim]\n"
        )

    # Exports.
    handle_exports(
        person=person,
        console=console,
        export_pdf=export_pdf,
        export_json=export_json,
        export_canvas=export_canvas,
        export_html=export_html,
        language=language,
    )
