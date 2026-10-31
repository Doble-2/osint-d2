"""Consoles, option validation, and AI and proxy configuration shared by commands."""

from __future__ import annotations

import json
import os
import sys
from enum import Enum

import typer
from rich.console import Console
from rich.prompt import Prompt

from core.config import AI_PROVIDER_PRESETS, AppSettings, write_user_env_vars
from core.domain.language import Language
from core.domain.models import PersonEntity

out_console = Console()
err_console = Console(stderr=True)
PROXY_MODES = ("residential", "datacenter")
AI_PROVIDER_HELP = f"AI provider preset: {', '.join(AI_PROVIDER_PRESETS)}."


def split_csv(values: list[str] | None) -> list[str]:
    """Flatten repeated, comma-separated option values, keeping the order."""
    items = (item.strip() for value in values or [] for item in value.split(","))
    return list(dict.fromkeys(item for item in items if item))


def validate_trust(trust: list[str] | None) -> list[str]:
    """Reject malformed anchors before any scan starts."""
    from core.services.trust_anchor import TrustAnchor

    for anchor in trust or []:
        try:
            TrustAnchor.parse(anchor)
        except ValueError as exc:
            raise typer.BadParameter(f"--trust '{anchor}': {exc}") from exc
    return trust or []


def validate_ai_options(*, analysis: bool, ai_provider: str | None, ai_key: str | None) -> None:
    """Reject AI options that would otherwise be silently ignored."""
    if ai_provider and ai_provider.strip().lower() not in AI_PROVIDER_PRESETS:
        raise typer.BadParameter(
            f"Unknown --ai-provider '{ai_provider}'. Choices: {', '.join(AI_PROVIDER_PRESETS)}"
        )
    if (ai_provider or ai_key) and not analysis:
        raise typer.BadParameter("--ai-provider and --ai-key need AI analysis; add --deep-analyze or --ai.")
    if ai_key and not ai_provider:
        raise typer.BadParameter("--ai-key needs --ai-provider, so the key goes to the right service.")


def apply_proxy_overrides(
    settings: AppSettings,
    *,
    proxy: str | None,
    no_proxy: bool,
    proxy_country: str | None,
) -> AppSettings:
    """Apply CLI proxy overrides to settings via env vars, then reload."""
    if proxy and proxy not in PROXY_MODES:
        raise typer.BadParameter(f"Unknown --proxy '{proxy}'. Choices: {', '.join(PROXY_MODES)}")
    if proxy_country and not (len(proxy_country) == 2 and proxy_country.isalpha()):
        raise typer.BadParameter("--proxy-country needs a 2-letter country code, such as 'us'.")
    if no_proxy:
        os.environ["OSINT_D2_PROXY_MODE"] = ""
        os.environ["OSINT_D2_PROXY_API_KEY"] = ""
        return AppSettings()
    if proxy:
        os.environ["OSINT_D2_PROXY_MODE"] = proxy
    if proxy_country:
        os.environ["OSINT_D2_PROXY_COUNTRY"] = proxy_country
    if proxy or proxy_country:
        return AppSettings()
    return settings


def print_proxy_status(settings: AppSettings, console: Console) -> None:
    mode = settings.effective_proxy_mode
    if mode:
        country = f" ({settings.proxy_country.upper()})" if settings.proxy_country else ""
        console.print(
            f"  [bright_cyan]🔒 Proxy:[/bright_cyan] "
            f"[green]{mode}{country}[/green] via ScrapingAnt\n"
        )


def configure_ai_for_run(
    *,
    settings: AppSettings,
    ai_provider: str | None,
    ai_key: str | None,
    ai_save: bool,
    interactive: bool,
    console: Console,
) -> AppSettings:
    """Aplica un preset de IA para esta ejecución y (opcionalmente) lo persiste.

    UX objetivo:
    - Usuarios PyInstaller: elegir proveedor + pegar key 1 vez.
    - Runs posteriores: no pedir nada (lee config global del usuario).
    """

    provider = (ai_provider or "").strip().lower() or None
    if not provider:
        return settings

    preset = AI_PROVIDER_PRESETS.get(provider)
    if not preset:
        raise typer.BadParameter(
            f"Unknown --ai-provider '{provider}'. Choices: {', '.join(sorted(AI_PROVIDER_PRESETS.keys()))}"
        )

    base_url = preset["base_url"]
    model = preset["model"]

    # A key configured for another provider must never be sent to this one.
    configured_key = settings.ai_api_key.get_secret_value() if settings.ai_api_key and settings.key_belongs_to(provider) else ""
    key = (ai_key or "").strip() or configured_key.strip()

    # Para proveedores locales (Ollama), la key es opcional/dummy.
    if provider == "ollama" and not key:
        key = "ollama"

    if not key and interactive:
        console.print(
            "[yellow]AI provider selected but no API key found.[/yellow] "
            "Paste it now."
        )
        key = Prompt.ask("AI API key", password=True).strip()

    os.environ["OSINT_D2_AI_PROVIDER"] = provider
    os.environ["OSINT_D2_AI_BASE_URL"] = base_url
    os.environ["OSINT_D2_AI_MODEL"] = model
    os.environ["OSINT_D2_AI_API_KEY"] = key

    if ai_save and key:
        env_path = write_user_env_vars(
            {
                "OSINT_D2_AI_PROVIDER": provider,
                "OSINT_D2_AI_BASE_URL": base_url,
                "OSINT_D2_AI_MODEL": model,
                "OSINT_D2_AI_API_KEY": key,
            }
        )
        err_console.print(f"[green]AI config saved to:[/green] {env_path}")

    return AppSettings()


class OutputFormat(str, Enum):
    table = "table"
    json = "json"


class NsfwPolicy(str, Enum):
    inherit = "inherit"
    exclude = "exclude"
    allow = "allow"


def auto_output_format(output_format: OutputFormat | None) -> OutputFormat:
    """Without an explicit --format: tables in a terminal, JSON when piped."""
    if output_format is not None:
        return output_format
    if sys.stdout.isatty():
        return OutputFormat.table
    err_console.print("[yellow]stdout is not a terminal; using JSON. Pass --format table to keep tables.[/yellow]")
    return OutputFormat.json


def resolve_language(language: Language | None) -> Language:
    if language is not None:
        return language
    return AppSettings().default_language


def dump_person_json(*, person: PersonEntity, include_raw: bool) -> str:
    data = person.model_dump(mode="json")
    if not include_raw:
        analysis = data.get("analysis")
        if isinstance(analysis, dict):
            analysis.pop("raw", None)
    return json.dumps(data, ensure_ascii=False)


def normalize_email(value: str) -> str:
    email = value.strip().lower()
    if "@" not in email:
        raise typer.BadParameter("Invalid email: missing '@'.")
    local, _, domain = email.partition("@")
    if not local or not domain or "." not in domain:
        raise typer.BadParameter("Invalid email address.")
    return email
