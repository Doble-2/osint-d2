"""Doctor command for environment diagnostics."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from adapters.http_client import build_async_client
from adapters.report_exporter import export_person_pdf
from core.config import AppSettings
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
        export_person_pdf(person=person, output_path=tmp)
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
    table.add_column("Check", style="cyan", no_wrap=True)
    table.add_column("Status", style="white")
    table.add_column("Details", style="dim")

    # Config
    table.add_row(
        "AI key (.env)",
        "OK" if bool(settings.ai_api_key) else "MISSING",
        "Set OSINT_D2_AI_API_KEY in .env",
    )
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
