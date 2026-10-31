"""`wizard`: guided investigations."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.prompt import Confirm, IntPrompt, Prompt

from cli.ui_components import print_banner
from core.config import AppSettings, write_user_env_vars
from core.domain.language import Language
from core.resources_loader import get_default_list_path
from cli.app import app
from core.config import AI_PROVIDER_PRESETS
from cli.shared import (
    OutputFormat, apply_proxy_overrides, normalize_email, out_console,
)
from cli.output import ask_trust_anchors
from cli.commands.agent import agent_async
from cli.commands.scanning import hunt_async


def _prompt_ai_setup(*, default: str) -> bool:
    """Ask for an AI provider and save it to the user config. False if incomplete."""
    provider = Prompt.ask("Provider", choices=list(AI_PROVIDER_PRESETS), default=default).strip().lower()
    preset = AI_PROVIDER_PRESETS[provider]
    base_url = Prompt.ask("AI base URL", default=preset["base_url"]).strip()
    model = Prompt.ask("AI model", default=preset["model"]).strip()
    api_key = Prompt.ask("AI API key", password=True, default="", show_default=False).strip()

    if not base_url or not model or (not api_key and provider != "ollama"):
        return False

    values = {"OSINT_D2_AI_PROVIDER": provider, "OSINT_D2_AI_BASE_URL": base_url, "OSINT_D2_AI_MODEL": model}
    if api_key:
        values["OSINT_D2_AI_API_KEY"] = api_key
    env_path = write_user_env_vars(values)
    out_console.print(f"[green]AI config saved to:[/green] {env_path}")
    return True


@app.command(help="Step-by-step interactive assistant for newcomers.")
def wizard() -> None:
    console = out_console
    print_banner(console)

    settings = AppSettings()
    mode = Prompt.ask(
        "What do you want to hunt?",
        choices=["username", "email", "both", "agent"],
        default="both",
        console=console,
    )

    # ── Agent mode (autonomous AI investigation) ──────────────────────
    if mode == "agent":
        objective = Prompt.ask("Investigation objective (username, email, or free text)").strip()
        if not objective:
            console.print("[red]Need an objective for the agent.[/red]")
            raise typer.Exit(code=2)

        default_language = settings.default_language.label().lower()
        language_choice = Prompt.ask(
            "Output language (english/spanish/portuguese/arabic/russian)",
            choices=["english", "spanish", "portuguese", "arabic", "russian"],
            default=default_language,
        )
        language = Language.from_str(language_choice)

        max_steps = IntPrompt.ask("Max reasoning steps", default=10)
        breach_check = Confirm.ask("Allow agent to check breaches (HIBP)?", default=False)

        # ── Proxy ──
        proxy_mode: str | None = None
        proxy_country: str | None = None
        if settings.proxy_api_key:
            use_proxy = Confirm.ask(
                "Use proxy? (ScrapingAnt detected in .env)", default=True,
            )
            if use_proxy:
                proxy_mode = Prompt.ask(
                    "Proxy mode",
                    choices=["residential", "datacenter"],
                    default="residential",
                )
                pc = Prompt.ask(
                    "Proxy country (2-letter code, or empty for any)",
                    default="",
                ).strip()
                if pc:
                    proxy_country = pc

        # ── Trust anchors ──
        trust_anchors = ask_trust_anchors(console)

        export_json = Confirm.ask("Export JSON to reports/?", default=False)
        export_pdf = Confirm.ask("Export PDF/HTML to reports/?", default=False)

        # Ensure AI is configured.
        settings_now = AppSettings()
        if not (settings_now.ai_api_key.get_secret_value() if settings_now.ai_api_key else "").strip():
            console.print(
                "[yellow]Agent mode requires an AI provider.[/yellow]"
            )
            if Confirm.ask("Configure AI provider now?", default=True):
                if not _prompt_ai_setup(default="deepseek"):
                    console.print("[red]AI provider is required for agent mode.[/red]")
                    raise typer.Exit(code=2)

        final_settings = apply_proxy_overrides(
            AppSettings(),
            proxy=proxy_mode,
            no_proxy=False,
            proxy_country=proxy_country,
        )

        asyncio.run(
            agent_async(
                settings=final_settings,
                objective=objective,
                max_steps=max_steps,
                language=language,
                breach_check=breach_check,
                export_json=export_json,
                export_pdf=export_pdf,
                trust_anchors=trust_anchors,
            )
        )
        return

    # ── Classic modes (username/email/both) ───────────────────────────
    usernames: list[str] | None

    if mode in ("username", "both"):
        u = Prompt.ask("Comma-separated usernames", default="").strip()
        usernames = [x.strip() for x in u.split(",") if x.strip()] if u else None
    else:
        usernames = None

    if mode in ("email", "both"):
        e = Prompt.ask("Comma-separated emails", default="").strip()
        emails = [normalize_email(x.strip()) for x in e.split(",") if x.strip()] if e else None
    else:
        emails = None

    if not usernames and not emails:
        console.print("[red]Need at least one username or email.[/red]")
        raise typer.Exit(code=2)

    default_language = settings.default_language.label().lower()
    language_choice = Prompt.ask(
        "Output language (english/spanish/portuguese/arabic/russian)",
        choices=["english", "spanish", "portuguese", "arabic", "russian"],
        default=default_language,
    )
    language = Language.from_str(language_choice)

    use_site_lists = Confirm.ask("Enable large site-lists engine?", default=False)
    use_sherlock = Confirm.ask("Enable Sherlock (400+ sites)?", default=False)
    strict = Confirm.ask("Strict mode (trim false positives)?", default=False)
    breach_check = False
    if emails:
        breach_check = Confirm.ask("Check emails against breach sources (HaveIBeenPwned)?", default=False)

    username_sites_path: Path | None = None
    email_sites_path: Path | None = None
    sites_max_concurrency: int | None = None
    no_nsfw: bool | None = None
    category: set[str] | None = None

    if use_site_lists:
        if usernames:
            default_u = ""
            if settings.username_sites_path:
                default_u = str(settings.username_sites_path)
            else:
                auto = get_default_list_path("wmn-data.json")
                if auto:
                    default_u = str(auto)
            p = Prompt.ask("Username site-list JSON path (wmn-data.json)", default=default_u).strip()
            username_sites_path = Path(p) if p else (Path(default_u) if default_u else None)
        if emails:
            default_e = ""
            if settings.email_sites_path:
                default_e = str(settings.email_sites_path)
            else:
                auto = get_default_list_path("email-data.json")
                if auto:
                    default_e = str(auto)
            p = Prompt.ask("Email site-list JSON path (email-data.json)", default=default_e).strip()
            email_sites_path = Path(p) if p else (Path(default_e) if default_e else None)

        sites_max_concurrency = IntPrompt.ask(
            "Max concurrency for site-lists",
            default=int(settings.sites_max_concurrency),
        )
        no_nsfw = Confirm.ask("Exclude NSFW categories?", default=bool(settings.sites_no_nsfw))
        cats = Prompt.ask("Categories (optional, comma-separated)", default="").strip()
        if cats:
            category = {c.strip().lower() for c in cats.split(",") if c.strip()} or None

    scan_localpart = False
    if emails:
        scan_localpart = Confirm.ask("Also try local part as username?", default=True)

    deep_analyze = Confirm.ask("Run AI analysis?", default=True)
    if deep_analyze:
        settings_now = AppSettings()
        if not (settings_now.ai_api_key.get_secret_value() if settings_now.ai_api_key else "").strip() and settings_now.ai_provider.lower() == "deepseek":
            if Confirm.ask("No AI key configured. Configure an AI provider now?", default=True):
                if not _prompt_ai_setup(default="deepseek"):
                    out_console.print("[yellow]Skipping remote AI setup; using heuristic fallback.[/yellow]")
    export_json = Confirm.ask("Export JSON to reports/?", default=False)
    export_pdf = Confirm.ask("Export PDF/HTML to reports/?", default=False)

    # ── Proxy ──
    wiz_proxy_mode: str | None = None
    wiz_proxy_country: str | None = None
    if settings.proxy_api_key:
        wiz_use_proxy = Confirm.ask(
            "Use proxy? (ScrapingAnt detected in .env)", default=True,
        )
        if wiz_use_proxy:
            wiz_proxy_mode = Prompt.ask(
                "Proxy mode",
                choices=["residential", "datacenter"],
                default="residential",
            )
            wpc = Prompt.ask(
                "Proxy country (2-letter code, or empty for any)",
                default="",
            ).strip()
            if wpc:
                wiz_proxy_country = wpc

    # ── Trust anchors ──
    wiz_trust_anchors = ask_trust_anchors(console)


    wiz_final_settings = apply_proxy_overrides(
        AppSettings(),
        proxy=wiz_proxy_mode,
        no_proxy=False,
        proxy_country=wiz_proxy_country,
    )

    asyncio.run(
        hunt_async(
            settings=wiz_final_settings,
            usernames=usernames,
            emails=emails,
            deep_analyze=deep_analyze,
            export_pdf=export_pdf,
            export_json=export_json,
            output_format=OutputFormat.table,
            include_raw_in_json=False,
            scan_localpart=scan_localpart,
            use_site_lists=use_site_lists,
            username_sites_path=username_sites_path,
            email_sites_path=email_sites_path,
            sites_max_concurrency=sites_max_concurrency,
            categories=category,
            no_nsfw=no_nsfw,
            use_sherlock=use_sherlock,
            strict=strict,
            language=language,
            breach_check=breach_check,
            trust_anchors=wiz_trust_anchors,
        )
    )
