"""Doctor command for environment diagnostics."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from adapters.http_client import build_async_client
from adapters.report_exporter import export_person_pdf
from core.config import AI_PROVIDER_PRESETS, AppSettings, write_user_env_vars
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
        with tempfile.TemporaryDirectory() as tmp:
            person = PersonEntity(target="doctor", profiles=[])
            export_person_pdf(person=person, output_path=Path(tmp) / "doctor.pdf", language=Language.ENGLISH)
        return True, "OK"
    except Exception as exc:
        return False, str(exc)


def _check_chromium() -> tuple[bool, str]:
    """Check that Playwright's browser, used for dashboard PDFs and graphs, exists."""

    async def probe() -> str:
        from playwright.async_api import async_playwright

        async with async_playwright() as playwright:
            return playwright.chromium.executable_path

    try:
        path = asyncio.run(probe())
    except Exception as exc:
        return False, str(exc)
    return Path(path).exists(), path


@app.command()
def run() -> None:
    """Run baseline diagnostics and show how to fix what fails."""

    settings = AppSettings()
    fixes: list[str] = []
    failed = False

    table = Table(title="OSINT-D2 Doctor")
    table.add_column("Check", style="bright_green", no_wrap=True)
    table.add_column("Status", style="white")
    table.add_column("Details", style="dim")

    # Config
    table.add_row("AI provider", "OK", settings.ai_provider)
    if settings.ai_api_key:
        table.add_row("AI key", "OK", "Configured")
    elif settings.ai_provider.lower() == "ollama":
        table.add_row("AI key", "OK", "Not needed for Ollama")
    else:
        table.add_row("AI key", "[yellow]MISSING[/yellow]", "`agent` fails; AI analysis uses a local heuristic.")
        fixes.append("AI key: run `osint-d2 doctor setup-ai` or set OSINT_D2_AI_API_KEY.")
    table.add_row("AI base_url", "OK", settings.ai_base_url)
    table.add_row("AI model", "OK", settings.ai_model)

    if settings.hibp_api_key:
        table.add_row("HIBP key", "OK", "Configured")
    else:
        table.add_row("HIBP key", "OFF", "Breach checks are unavailable. Set OSINT_D2_HIBP_API_KEY to use them.")

    # Connectivity (best-effort)
    ok_http, detail_http = asyncio.run(_check_http("https://github.com"))
    table.add_row("HTTP connectivity", "OK" if ok_http else "[red]FAIL[/red]", detail_http)
    if not ok_http:
        failed = True
        fixes.append("HTTP: check your network connection and proxy settings.")

    # PDF
    ok_pdf, detail_pdf = _check_pdf()
    table.add_row("WeasyPrint PDF", "OK" if ok_pdf else "[red]FAIL[/red]", detail_pdf)
    if not ok_pdf:
        failed = True
        fixes.append(
            "PDF: install Cairo, Pango, and GDK-Pixbuf (see the installation guide). "
            "Until then, --export-pdf falls back to HTML."
        )

    # Chromium
    ok_chromium, detail_chromium = _check_chromium()
    table.add_row("Chromium", "OK" if ok_chromium else "[red]FAIL[/red]", detail_chromium)
    if not ok_chromium:
        failed = True
        fixes.append("Chromium: run `playwright install chromium`. Dashboard PDFs and graphs need it.")

    # Proxy (ScrapingAnt)
    proxy_mode = settings.effective_proxy_mode
    if proxy_mode:
        raw_key = settings.proxy_api_key.get_secret_value() if settings.proxy_api_key else ""
        key_masked = "****" + raw_key[-4:] if raw_key else "(none)"
        country = settings.proxy_country.upper() if settings.proxy_country else "auto"
        table.add_row("Proxy mode", "OK", f"{proxy_mode} (ScrapingAnt)")
        table.add_row("Proxy API key", "OK", key_masked)
        table.add_row("Proxy country", "OK", country)
    else:
        table.add_row("Proxy mode", "OFF", "Direct connections (no proxy)")

    _console.print(table)

    if fixes:
        _console.print("\n[bold]How to fix:[/bold]")
        for fix in fixes:
            _console.print(f"  - {fix}", markup=False)

    if failed:
        raise typer.Exit(code=1)


@app.command(name="setup-ai")
def setup_ai() -> None:
    """Interactive AI setup (stores config in the user config .env).

    Designed for PyInstaller/non-Python users: no manual .env editing.
    """

    provider = typer.prompt(
        f"AI provider ({', '.join(AI_PROVIDER_PRESETS)})",
        default="deepseek",
        show_default=True,
    ).strip().lower()

    preset = AI_PROVIDER_PRESETS.get(provider, {})
    if not preset:
        _console.print("[yellow]Unknown provider preset. You can still enter custom values.[/yellow]")

    base_url = typer.prompt("AI base URL", default=preset.get("base_url", ""), show_default=True).strip()
    model = typer.prompt("AI model", default=preset.get("model", ""), show_default=True).strip()
    api_key = typer.prompt("AI API key (leave blank to keep the saved one)", hide_input=True, default="", show_default=False).strip()

    if not base_url or not model:
        raise typer.BadParameter("base_url and model are required")

    values = {
        "OSINT_D2_AI_PROVIDER": provider,
        "OSINT_D2_AI_BASE_URL": base_url,
        "OSINT_D2_AI_MODEL": model,
    }
    # A blank answer keeps the saved key instead of erasing it.
    if api_key:
        values["OSINT_D2_AI_API_KEY"] = api_key
    env_path = write_user_env_vars(values)

    _console.print(f"[green]Saved AI config to:[/green] {env_path}")
