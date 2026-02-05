"""Doctor command for environment diagnostics."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from adapters.http_client import build_async_client
from adapters.report_exporter import export_person_pdf
from core.config import AppSettings, write_user_env_vars
from core.domain.language import Language
from core.domain.models import PersonEntity

app = typer.Typer(no_args_is_help=True, help="Environment diagnostics and configuration checks.")

_console = Console()


async def _check_http(url: str) -> tuple[bool, str]:
    try:
        async with build_async_client() as client:
            response = await client.get(url)
        return True, f"HTTP {response.status_code}"
    except Exception as exc:
        return False, str(exc)


def _check_pdf() -> tuple[bool, str]:
    """Attempt to generate a minimal PDF to detect WeasyPrint issues."""

    try:
        tmp = Path("reports") / "_doctor_test.pdf"
        person = PersonEntity(target="doctor", profiles=[])
        export_person_pdf(person=person, output_path=tmp, language=Language.ENGLISH)
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        return True, "OK"
    except Exception as exc:
        return False, str(exc)


@app.command()
def run() -> None:
    """Run baseline diagnostics and show recommended fixes."""

    settings = AppSettings()

    table = Table(title="OSINT-D2 Doctor")
    table.add_column("Check", style="bright_green", no_wrap=True)
    table.add_column("Status", style="white")
    table.add_column("Details", style="dim")

    # Config
    if bool(settings.ai_api_key):
        table.add_row("AI key", "OK", "Remote AI enabled")
    else:
        table.add_row("AI key", "OPTIONAL", "No key set -> heuristic analysis fallback")
    table.add_row("AI base_url", "OK", settings.ai_base_url)
    table.add_row("AI model", "OK", settings.ai_model)

    # Connectivity (best-effort)
    ok_http, detail_http = asyncio.run(_check_http("https://github.com"))
    table.add_row("HTTP connectivity", "OK" if ok_http else "FAIL", detail_http)

    # PDF
    ok_pdf, detail_pdf = _check_pdf()
    table.add_row("WeasyPrint PDF", "OK" if ok_pdf else "FAIL", detail_pdf)

    _console.print(table)

    if not ok_pdf:
        _console.print(
            "\n[yellow]Note:[/yellow] When PDF export fails, `--export-pdf` automatically falls back to HTML."
        )


@app.command(name="setup-ai")
def setup_ai() -> None:
    """Interactive AI setup (stores config in the user config .env).

    Designed for PyInstaller/non-Python users: no manual .env editing.
    """

    provider = typer.prompt(
        "AI provider",
        default="groq",
        show_default=True,
    ).strip().lower()

    presets: dict[str, dict[str, str]] = {
        "deepseek": {"OSINT_D2_AI_BASE_URL": "https://api.deepseek.com", "OSINT_D2_AI_MODEL": "deepseek-chat"},
        # Calidad (más lento, mejor para informes):
        "groq": {"OSINT_D2_AI_BASE_URL": "https://api.groq.com/openai/v1", "OSINT_D2_AI_MODEL": "llama-3.1-70b-versatile"},
        "groq-70b": {"OSINT_D2_AI_BASE_URL": "https://api.groq.com/openai/v1", "OSINT_D2_AI_MODEL": "llama-3.1-70b-versatile"},
        # Velocidad:
        "groq-fast": {"OSINT_D2_AI_BASE_URL": "https://api.groq.com/openai/v1", "OSINT_D2_AI_MODEL": "llama-3.1-8b-instant"},
        "openrouter": {"OSINT_D2_AI_BASE_URL": "https://openrouter.ai/api/v1", "OSINT_D2_AI_MODEL": "openai/gpt-4o-mini"},
        "huggingface": {"OSINT_D2_AI_BASE_URL": "https://api-inference.huggingface.co/v1", "OSINT_D2_AI_MODEL": "meta-llama/Llama-3.1-8B-Instruct"},
        "ollama": {"OSINT_D2_AI_BASE_URL": "http://localhost:11434/v1", "OSINT_D2_AI_MODEL": "llama3"},
    }

    values = presets.get(provider, {}).copy()
    if not values:
        _console.print("[yellow]Unknown provider preset. You can still enter custom values.[/yellow]")

    base_url = typer.prompt("AI base URL", default=values.get("OSINT_D2_AI_BASE_URL", ""), show_default=True).strip()
    model = typer.prompt("AI model", default=values.get("OSINT_D2_AI_MODEL", ""), show_default=True).strip()
    api_key = typer.prompt("AI API key", hide_input=True, confirmation_prompt=False).strip()

    if not base_url or not model:
        raise typer.BadParameter("base_url and model are required")

    env_path = write_user_env_vars(
        {
            "OSINT_D2_AI_BASE_URL": base_url,
            "OSINT_D2_AI_MODEL": model,
            "OSINT_D2_AI_API_KEY": api_key,
        }
    )

    _console.print(f"[green]Saved AI config to:[/green] {env_path}")
