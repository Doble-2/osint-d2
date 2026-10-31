"""Terminal tables, report exports, and the trust anchor prompt."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.prompt import Confirm, Prompt

from adapters.report_store import purge_expired
from core.config import AppSettings
from adapters.json_exporter import export_person_json
from adapters.report_exporter import export_person_html, export_person_pdf
from cli.ui_components import build_breaches_table, build_profiles_table
from core.domain.language import Language
from core.domain.models import PersonEntity
from core.services.identity_pipeline import (
    sanitize_target_for_filename,
)
from cli.shared import out_console


def print_profiles_table(*, person: PersonEntity, primary_usernames: list[str]) -> None:
    main_set = {username.lower() for username in primary_usernames if username}
    main_profiles: list = []
    extra_profiles: list = []
    for profile in person.profiles:
        username_value = (profile.username or "").lower()
        if username_value and username_value in main_set:
            main_profiles.append(profile)
        else:
            extra_profiles.append(profile)

    main_profiles.sort(key=lambda p: (p.username or "").lower())
    extra_profiles.sort(key=lambda p: (p.username or "").lower())

    table = build_profiles_table()
    for profile in main_profiles + extra_profiles:
        err = ""
        if isinstance(profile.metadata, dict):
            maybe_err = profile.metadata.get("error")
            if isinstance(maybe_err, str):
                err = maybe_err
        table.add_row(
            profile.network_name,
            profile.username,
            "YES" if profile.exists else "NO",
            str(profile.url),
            err,
        )
    out_console.print(table)


def print_breaches_table(*, person: PersonEntity) -> None:
    hibp_profiles = [p for p in person.profiles if (p.network_name or "").lower() == "hibp"]
    if not hibp_profiles:
        return

    table = build_breaches_table()
    printed_rows = 0

    for profile in sorted(hibp_profiles, key=lambda p: (p.username or "").lower()):
        md = profile.metadata if isinstance(profile.metadata, dict) else {}
        status_code = md.get("status_code")
        error = md.get("error")
        status_text = "" if status_code is None else str(status_code)
        error_text = str(error) if isinstance(error, str) else ""
        email_value = profile.username

        breaches_dump = md.get("breaches")
        breaches_list = []
        if isinstance(breaches_dump, dict):
            maybe = breaches_dump.get("breaches")
            if isinstance(maybe, list):
                breaches_list = [b for b in maybe if isinstance(b, dict)]

        if status_code != 200:
            table.add_row(
                email_value,
                "-",
                "-",
                "-",
                "-",
                "-",
                status_text,
                error_text or f"hibp_http_{status_text}" if status_text else "hibp_no_response",
            )
            printed_rows += 1
            continue

        if not breaches_list:
            table.add_row(
                email_value,
                "(none)",
                "",
                "",
                "0",
                "",
                status_text,
                "",
            )
            printed_rows += 1
            continue

        for breach in breaches_list:
            title = str(breach.get("title") or "")
            domain = str(breach.get("domain") or "")
            date = str(breach.get("breach_date") or "")
            records = breach.get("pwn_count")
            records_text = str(records) if records is not None else ""
            data_classes = breach.get("data_classes")
            if isinstance(data_classes, list):
                classes_text = ", ".join(str(x) for x in data_classes if x is not None)
            else:
                classes_text = ""

            table.add_row(
                email_value,
                title,
                domain,
                date,
                records_text,
                classes_text,
                status_text,
                "",
            )
            printed_rows += 1

    if printed_rows:
        out_console.print(table)


def handle_exports(
    *,
    person: PersonEntity,
    console: Console,
    export_pdf: bool,
    export_json: bool,
    export_canvas: bool = False,
    export_html: bool = False,
    language: Language,
) -> None:
    if not export_pdf and not export_json and not export_canvas and not export_html:
        return

    purge_expired(AppSettings().report_retention_days)
    safe_name = sanitize_target_for_filename(person.target)
    reports_dir = Path("reports")
    reports_dir.mkdir(parents=True, exist_ok=True)

    if export_canvas or export_html:
        try:
            from adapters.graph_exporter import GraphExporter
            graph = GraphExporter.build_graph(person)
            if export_canvas:
                canvas_path = reports_dir / f"{safe_name}.canvas"
                GraphExporter.export_canvas(graph, canvas_path)
                console.print(f"\n[green]Obsidian Canvas graph generated:[/green] {canvas_path}")
            if export_html:
                html_graph_path = reports_dir / f"{safe_name}_graph.html"
                GraphExporter.export_html(graph, html_graph_path, title=f"OSINT Graph — {person.target}")
                console.print(f"[green]Interactive HTML graph generated:[/green] {html_graph_path}")
        except Exception as exc:
            console.print(f"\n[red]Graph export failed:[/red] {exc}")

    if export_pdf:
        try:
            out_path = Path("reports") / f"{safe_name}.pdf"
            export_person_pdf(person=person, output_path=out_path, language=language)
            console.print(f"\n[green]PDF generated:[/green] {out_path}")
        except Exception as exc:
            console.print(f"\n[red]PDF export failed:[/red] {exc}")
            html_path = Path("reports") / f"{safe_name}.html"
            try:
                export_person_html(person=person, output_path=html_path, language=language)
                console.print(f"[yellow]Fallback HTML generated:[/yellow] {html_path}")
            except Exception as html_exc:
                console.print(f"[red]HTML export failed:[/red] {html_exc}")

    if export_json:
        try:
            json_path = Path("reports") / f"{safe_name}.json"
            export_person_json(person=person, output_path=json_path)
            console.print(f"\n[green]JSON generated:[/green] {json_path}")
        except Exception as exc:
            console.print(f"\n[red]JSON export failed:[/red] {exc}")


def ask_trust_anchors(console: Console) -> list[str]:
    """Interactive prompt to collect trust anchors.

    Handles multiple anchors per line (comma or space separated).
    """
    anchors: list[str] = []
    use_trust = Confirm.ask(
        "Add trusted identity sources? (e.g. instagram:user, email:user@mail.com)",
        default=False,
    )
    if not use_trust:
        return anchors

    console.print(
        "  [dim]Format: network:username or email:user@domain.com[/dim]\n"
        "  [dim]Examples: github:johndoe  email:john@example.com[/dim]\n"
        "  [dim]You can enter multiple per line (comma or space separated).[/dim]\n"
        "  [dim]Empty line to finish.[/dim]"
    )
    while True:
        raw = Prompt.ask("  Trust anchor(s)", default="").strip()
        if not raw:
            break
        # Split by comma or whitespace
        parts = [p.strip() for p in raw.replace(",", " ").split() if p.strip()]
        for part in parts:
            if ":" not in part:
                console.print(f"  [yellow]Skipped '{part}' — invalid format. Use network:username[/yellow]")
                continue
            anchors.append(part)
            console.print(f"  [green]  + {part}[/green]")

    if anchors:
        console.print(f"  [green]✓ {len(anchors)} trust anchor(s) registered[/green]")
    return anchors
