"""`phone`: telecom lookups."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import typer
from rich.markup import escape

from cli.app import app
from cli.shared import (
    OutputFormat, auto_output_format, err_console, out_console,
)


@app.command(name="phone", help="Telecom intelligence and reverse footprint lookup on a phone number.")
def phone(
    phone_number: str = typer.Argument(..., help="Target phone number (e.g. +12125551234, +442071234567)."),
    default_region: str = typer.Option("US", "--region", "-r", help="Default ISO country code if international prefix is omitted (default: US)."),
    export_json: bool = typer.Option(False, "--export-json", help="Export phone intelligence report to JSON."),
    output_format: OutputFormat | None = typer.Option(
        None,
        "--format",
        help="Output format: table or json. Defaults to table in a terminal and json when piped.",
        show_default=False,
    ),
) -> None:
    """Telecom analysis, carrier, WhatsApp presence and footprint dorks."""
    import dataclasses

    from adapters.phone_scanner import PhoneScanner
    from rich.table import Table

    output_format = auto_output_format(output_format)
    human = output_format == OutputFormat.table
    console = out_console if human else err_console

    async def _run_phone():
        with console.status(f"[cyan]Scanning phone number [bold]{escape(phone_number)}[/bold]...", spinner="dots"):
            return await PhoneScanner.scan(phone_number, default_region=default_region)

    result = asyncio.run(_run_phone())

    if not result.is_valid:
        err_console.print(f"[red]Error:[/red] {escape(result.error or 'Invalid phone number format.')}")
        raise typer.Exit(code=1)

    if not human:
        sys.stdout.write(json.dumps(dataclasses.asdict(result), ensure_ascii=False) + "\n")

    table = Table(title="[bold cyan]Telecom & Geotemporal Intelligence[/bold cyan]", border_style="cyan")
    table.add_column("Property", style="bold white")
    table.add_column("Value", style="green")

    table.add_row("E.164 Format", result.e164)
    table.add_row("Country", f"{result.country_name} ({result.country_iso}) [+{result.country_code}]")
    table.add_row("Carrier / Operator", result.carrier_name or "Unknown / Unassigned")
    table.add_row("Line Type", result.line_type)
    table.add_row("Timezone(s)", ", ".join(result.timezones) if result.timezones else "Unknown")
    wa_status = "[bold green]YES (Registered)[/bold green]" if result.whatsapp_active else "[yellow]No / Unknown[/yellow]"
    table.add_row("WhatsApp Active", wa_status)

    if human:
        console.print(table)

    if human and result.footprint_urls:
        dork_table = Table(title="[bold magenta]OSINT Footprint & Reverse Queries[/bold magenta]", border_style="magenta")
        dork_table.add_column("Service", style="bold yellow")
        dork_table.add_column("Footprint URL", style="cyan")
        for k, v in result.footprint_urls.items():
            dork_table.add_row(k.upper(), v)
        console.print(dork_table)

    if export_json:
        safe_num = "".join(ch for ch in result.e164 if ch.isdigit())
        out_dir = Path("reports")
        out_dir.mkdir(parents=True, exist_ok=True)
        json_file = out_dir / f"phone_{safe_num}.json"
        json_file.write_text(json.dumps(dataclasses.asdict(result), indent=2, ensure_ascii=False))
        console.print(f"\n[green]JSON report generated:[/green] {json_file}")
