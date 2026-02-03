"""CLI entry point (Typer + Rich).

Why Typer + Rich:
- Typer (Click) delivers a modern CLI UX with autocompletion and clear help.
- Rich keeps terminal output readable with panels, tables, spinners, and styles.

Architecture note:
- This layer *orchestrates*; it does not embed scraping or business rules.
- Any I/O heavy operation lives in async helpers executed through
    `asyncio.run(...)` so Typer commands remain synchronous.
"""

from __future__ import annotations

import asyncio
import errno
import json
import os
import signal
import sys
from contextlib import suppress
from enum import Enum
from pathlib import Path

import typer
from rich.console import Console
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from adapters.ai_analyst import analyze_person
from adapters.json_exporter import export_person_json
from adapters.report_exporter import export_person_html, export_person_pdf
from cli.doctor import app as doctor_app
from cli.ui_components import build_analysis_panel, build_profiles_table, print_banner
from core.config import AppSettings
from core.domain.language import Language
from core.domain.models import PersonEntity
from core.resources_loader import get_default_list_path
from core.services.identity_pipeline import (
    HuntRequest,
    PipelineHooks,
    SiteListOptions,
    sanitize_target_for_filename,
    hunt as run_hunt_pipeline,
    scan_email as run_email_pipeline,
    scan_username as run_username_pipeline,
)
# TODO: arreglar las advertencias de pylance
app = typer.Typer(
    name="osint-d2",
    no_args_is_help=False,
    help=(
        "OSINT-D2: modern OSINT toolkit to investigate and profile identities.\n\n"
        "Key commands:\n"
        "  scan         -> Quick sweep for a username.\n"
        "  scan-email   -> Correlate data starting from an email.\n"
        "  hunt         -> Full pipeline (usernames, emails, Sherlock, site-lists).\n"
        "  analyze      -> Reprocess an exported JSON with the AI engine.\n"
        "  wizard       -> Guided workflow for interactive runs.\n"
        "  doctor       -> Environment diagnostics and utilities.\n"
        "  breach      -> Check if credentials have been leaked (BreachDirectory).\n\n"
        "Use `osint-d2 <command> --help` for detailed flags."
    ),
)
app.add_typer(doctor_app, name="doctor")

_console = Console()

try:
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
except Exception:
    pass


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            typer.echo(ctx.get_help())
            raise typer.Exit(code=0)
        wizard()


class OutputFormat(str, Enum):
    table = "table"
    json = "json"


class NsfwPolicy(str, Enum):
    inherit = "inherit"
    exclude = "exclude"
    allow = "allow"


def _auto_output_format(output_format: OutputFormat) -> OutputFormat:
    if output_format == OutputFormat.table and not sys.stdout.isatty():
        Console(stderr=True).print(
            "[yellow]stdout is not a TTY; auto-switching to --format json. Pass --format table to force tables.[/yellow]"
        )
        return OutputFormat.json
    return output_format


def _resolve_language(spanish_flag: bool | None) -> Language:
    if spanish_flag is True:
        return Language.SPANISH
    if spanish_flag is False:
        return Language.ENGLISH
    return AppSettings().default_language


def _dump_person_json(*, person: PersonEntity, include_raw: bool) -> str:
    data = person.model_dump(mode="json")
    if not include_raw:
        analysis = data.get("analysis")
        if isinstance(analysis, dict):
            analysis.pop("raw", None)
    return json.dumps(data, ensure_ascii=False)


def _normalize_email(value: str) -> str:
    email = value.strip().lower()
    if "@" not in email:
        raise typer.BadParameter("Invalid email: missing '@'.")
    local, _, domain = email.partition("@")
    if not local or not domain or "." not in domain:
        raise typer.BadParameter("Invalid email address.")
    return email


def _print_profiles_table(*, person: PersonEntity, primary_usernames: list[str]) -> None:
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
            "YES" if profile.existe else "NO",
            str(profile.url),
            err,
        )
    _console.print(table)


def _handle_exports(
    *,
    person: PersonEntity,
    console: Console,
    export_pdf: bool,
    export_json: bool,
    language: Language,
) -> None:
    if not export_pdf and not export_json:
        return

    safe_name = sanitize_target_for_filename(person.target)

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


async def _hunt_async(
    *,
    usernames: list[str] | None,
    emails: list[str] | None,
    deep_analyze: bool,
    export_pdf: bool,
    export_json: bool,
    output_format: OutputFormat,
    include_raw_in_json: bool,
    scan_localpart: bool,
    use_site_lists: bool,
    username_sites_path: Path | None,
    email_sites_path: Path | None,
    sites_max_concurrency: int | None,
    categories: set[str] | None,
    no_nsfw: bool | None,
    use_sherlock: bool,
    strict: bool,
    language: Language,
) -> None:
    if not usernames and not emails:
        raise typer.BadParameter("Provide at least one username or email to hunt.")

    output_format = _auto_output_format(output_format)
    human = output_format == OutputFormat.table
    console = _console if human else Console(stderr=True)

    if human:
        print_banner(console)

    settings = AppSettings()
    status_ctx = console.status("Building aggregated intelligence...", spinner="dots") if human else None
    progress: Progress | None = None
    progress_task_id: int | None = None

    def close_status() -> None:
        nonlocal status_ctx
        if status_ctx:
            status_ctx.__exit__(None, None, None)
            status_ctx = None

    hooks = PipelineHooks(
        warning=lambda msg: console.print(f"[yellow]{msg}[/yellow]"),
    )

    if human:
        def on_sherlock_start(total: int) -> None:
            nonlocal progress, progress_task_id
            if total <= 0:
                return
            close_status()
            progress = Progress(
                SpinnerColumn(),
                TextColumn("[bright_green]Sherlock[/bright_green] {task.completed}/{task.total} ({task.percentage:>3.0f}%)"),
                BarColumn(bar_width=None),
                TimeElapsedColumn(),
                TimeRemainingColumn(),
                console=console,
                transient=True,
            )
            progress.__enter__()
            progress_task_id = progress.add_task("Sherlock", total=total)

        def on_sherlock_progress(done: int, _total: int, _site: str) -> None:
            if progress and progress_task_id is not None:
                progress.update(progress_task_id, completed=done)

        hooks.sherlock_start = on_sherlock_start
        hooks.sherlock_progress = on_sherlock_progress

    if status_ctx:
        status_ctx.__enter__()
    try:
        request = HuntRequest(
            usernames=usernames,
            emails=emails,
            scan_localpart=scan_localpart,
            site_lists=SiteListOptions(
                enabled=use_site_lists,
                username_path=username_sites_path,
                email_path=email_sites_path,
                max_concurrency=sites_max_concurrency,
                categories=categories,
                no_nsfw=no_nsfw,
            ),
            use_sherlock=use_sherlock,
            strict=strict,
        )
        result = await run_hunt_pipeline(
            settings=settings,
            request=request,
            hooks=hooks,
        )
    finally:
        close_status()
        if progress:
            progress.__exit__(None, None, None)

    person = result.person
    primary_usernames: list[str] = list(usernames or []) or ([result.usernames[0]] if result.usernames else [])

    if human:
        _print_profiles_table(person=person, primary_usernames=primary_usernames)

    if deep_analyze:
        await _analyze_async(
            person=person,
            output_format=output_format,
            emit_json=False,
            include_raw_in_json=include_raw_in_json,
            language=language,
        )

    _handle_exports(
        person=person,
        console=console,
        export_pdf=export_pdf,
        export_json=export_json,
        language=language,
    )

    if output_format == OutputFormat.json:
        sys.stdout.write(_dump_person_json(person=person, include_raw=include_raw_in_json))
        sys.stdout.write("\n")
        sys.stdout.flush()


async def _scan_async(
    *,
    target: str,
    deep_analyze: bool,
    export_pdf: bool,
    export_json: bool,
    output_format: OutputFormat,
    include_raw_in_json: bool,
    language: Language,
) -> None:
    output_format = _auto_output_format(output_format)
    human = output_format == OutputFormat.table
    console = _console if human else Console(stderr=True)

    if human:
        print_banner(console)

    status_ctx = console.status("Running baseline sources...", spinner="dots") if human else None
    if status_ctx:
        status_ctx.__enter__()
    try:
        result = await run_username_pipeline(settings=AppSettings(), username=target)
    finally:
        if status_ctx:
            status_ctx.__exit__(None, None, None)

    person = result.person

    if human:
        _print_profiles_table(person=person, primary_usernames=[target])

    if deep_analyze:
        await _analyze_async(
            person=person,
            output_format=output_format,
            emit_json=False,
            include_raw_in_json=include_raw_in_json,
            language=language,
        )

    _handle_exports(
        person=person,
        console=console,
        export_pdf=export_pdf,
        export_json=export_json,
        language=language,
    )

    if output_format == OutputFormat.json:
        sys.stdout.write(_dump_person_json(person=person, include_raw=include_raw_in_json))
        sys.stdout.write("\n")
        sys.stdout.flush()


async def _scan_email_async(
    *,
    email: str,
    deep_analyze: bool,
    export_pdf: bool,
    export_json: bool,
    output_format: OutputFormat,
    include_raw_in_json: bool,
    scan_localpart: bool,
    language: Language,
) -> None:
    output_format = _auto_output_format(output_format)
    human = output_format == OutputFormat.table
    console = _console if human else Console(stderr=True)

    if human:
        print_banner(console)

    status_ctx = console.status("Scanning email intelligence sources...", spinner="dots") if human else None
    if status_ctx:
        status_ctx.__enter__()
    try:
        result = await run_email_pipeline(
            settings=AppSettings(),
            email=email,
            scan_localpart=scan_localpart,
        )
    finally:
        if status_ctx:
            status_ctx.__exit__(None, None, None)

    person = result.person

    if human:
        _print_profiles_table(person=person, primary_usernames=[email])

    if deep_analyze:
        await _analyze_async(
            person=person,
            output_format=output_format,
            emit_json=False,
            include_raw_in_json=include_raw_in_json,
            language=language,
        )

    _handle_exports(
        person=person,
        console=console,
        export_pdf=export_pdf,
        export_json=export_json,
        language=language,
    )

    if output_format == OutputFormat.json:
        sys.stdout.write(_dump_person_json(person=person, include_raw=include_raw_in_json))
        sys.stdout.write("\n")
        sys.stdout.flush()


async def _analyze_async(
    *,
    person: PersonEntity,
    output_format: OutputFormat,
    emit_json: bool,
    include_raw_in_json: bool,
    language: Language,
) -> None:
    human = output_format == OutputFormat.table
    console = _console if human else Console(stderr=True)

    settings = AppSettings()
    if human:
        print_banner(console)

    try:
        status = console.status(
            f"Running AI profiler ({language.label()})...",
            spinner="dots",
        ) if human else None
        if status:
            status.__enter__()
        try:
            report = await analyze_person(person=person, language=language, settings=settings)
            person.analysis = report
        finally:
            if status:
                status.__exit__(None, None, None)

        if human:
            console.print(build_analysis_panel(report))
        elif emit_json:
            sys.stdout.write(_dump_person_json(person=person, include_raw=include_raw_in_json))
            sys.stdout.write("\n")
            sys.stdout.flush()
    except Exception as exc:
        console.print(f"\n[red]AI analysis failed:[/red] {exc}")

    if output_format == OutputFormat.json and not human:
        sys.stdout.write(_dump_person_json(person=person, include_raw=include_raw_in_json))
        sys.stdout.write("\n")
        sys.stdout.flush()


@app.command(help="Quick username sweep across the default intelligence sources.")
def scan(
    target: str = typer.Argument(..., help="Username or alias to investigate."),
    deep_analyze: bool = typer.Option(
        False,
        "--deep-analyze/--no-deep-analyze",
        help="Run the cognitive AI analysis (DeepSeek) on top of collected evidence.",
    ),
    spanish: bool | None = typer.Option(
        None,
        "--spanish/--english",
        "-s",
        help="Switch output language: --spanish for Spanish, --english for English (default).",
        show_default=False,
    ),
    export_pdf: bool = typer.Option(
        False,
        "--export-pdf/--no-export-pdf",
        help="Export a PDF dossier to reports/ (falls back to HTML on failure).",
    ),
    export_json: bool = typer.Option(
        False,
        "--export-json/--no-export-json",
        help="Export the aggregated entity (profiles + analysis) as JSON in reports/.",
    ),
    output_format: OutputFormat = typer.Option(
        OutputFormat.table,
        "--format",
        help="Terminal output format: table or json.",
    ),
    json_raw: bool = typer.Option(
        False,
        "--json-raw/--no-json-raw",
        help="(--format json) Include analysis.raw with the raw AI provider payload.",
    ),
) -> None:
    output_format = _auto_output_format(output_format)
    language = _resolve_language(spanish)
    asyncio.run(
        _scan_async(
            target=target,
            deep_analyze=deep_analyze,
            export_pdf=export_pdf,
            export_json=export_json,
            output_format=output_format,
            include_raw_in_json=json_raw,
            language=language,
        )
    )


@app.command(name="scan-email", help="Focused email pivoting across supported sources.")
def scan_email(
    email: str = typer.Argument(..., help="Target email address (e.g. user@example.com)."),
    deep_analyze: bool = typer.Option(
        True,
        "--deep-analyze/--no-deep-analyze",
        help="Run the cognitive AI analysis (DeepSeek) on top of collected evidence.",
    ),
    scan_localpart: bool = typer.Option(
        False,
        "--scan-localpart/--no-scan-localpart",
        help="Also try the username derived from the local part across username sources.",
    ),
    spanish: bool | None = typer.Option(
        None,
        "--spanish/--english",
        "-s",
        help="Switch output language: --spanish for Spanish, --english for English (default).",
        show_default=False,
    ),
    export_json: bool = typer.Option(
        False,
        "--export-json/--no-export-json",
        help="Export the aggregated entity (profiles + analysis) as JSON in reports/.",
    ),
    export_pdf: bool = typer.Option(
        False,
        "--export-pdf/--no-export-pdf",
        help="Export a PDF dossier (falls back to HTML on failure).",
    ),
    output_format: OutputFormat = typer.Option(
        OutputFormat.table,
        "--format",
        help="Terminal output format: table or json.",
    ),
    json_raw: bool = typer.Option(
        False,
        "--json-raw/--no-json-raw",
        help="(--format json) Include analysis.raw with the raw AI provider payload.",
    ),
) -> None:
    normalized = _normalize_email(email)
    output_format = _auto_output_format(output_format)
    language = _resolve_language(spanish)
    asyncio.run(
        _scan_email_async(
            email=normalized,
            deep_analyze=deep_analyze,
            export_pdf=export_pdf,
            export_json=export_json,
            output_format=output_format,
            include_raw_in_json=json_raw,
            scan_localpart=scan_localpart,
            language=language,
        )
    )


@app.command(help="Full OSINT hunt combining usernames, emails, Sherlock, and site-lists.")
def hunt(
    usernames: list[str] | None = typer.Option(
        None,
        "--usernames",
        "-u",
        help="Target usernames (comma-separated).",
    ),
    emails: list[str] | None = typer.Option(
        None,
        "--emails",
        "-e",
        help="Target emails (comma-separated).",
    ),
    ai: bool = typer.Option(
        True,
        "--ai/--noai",
        help="Run the cognitive AI analysis (DeepSeek) on top of collected evidence.",
    ),
    scan_localpart: bool = typer.Option(
        True,
        "--scan-localpart/--no-scan-localpart",
        help="When emails are present, also pivot using the local part on username sources.",
    ),
    use_site_lists: bool = typer.Option(
        False,
        "--site-lists/--no-site-lists",
        help="Enable the data-driven engine (large site lists like WhatsMyName/email-data).",
    ),
    username_sites_path: Path | None = typer.Option(
        None,
        "--username-sites-path",
        help="Local JSON path for username site lists (e.g. wmn-data.json).",
    ),
    email_sites_path: Path | None = typer.Option(
        None,
        "--email-sites-path",
        help="Local JSON path for email site lists (e.g. email-data.json).",
    ),
    sites_max_concurrency: int | None = typer.Option(
        None,
        "--sites-max-concurrency",
        min=1,
        max=500,
        help="Max concurrency for site-lists (defaults to OSINT_D2_SITES_MAX_CONCURRENCY).",
    ),
    category: list[str] | None = typer.Option(
        None,
        "--category",
        help="Filter site-lists by category (repeatable).",
    ),
    nsfw: NsfwPolicy = typer.Option(
        NsfwPolicy.inherit,
        "--nsfw",
        help="NSFW policy for site-lists: inherit|exclude|allow.",
    ),
    spanish: bool | None = typer.Option(
        None,
        "--spanish/--english",
        "-s",
        help="Switch output language: --spanish for Spanish, --english for English (default).",
        show_default=False,
    ),
    export_json: bool = typer.Option(
        False,
        "--export-json/--no-export-json",
        help="Export the aggregated entity (profiles + analysis) as JSON in reports/.",
    ),
    export_pdf: bool = typer.Option(
        False,
        "--export-pdf/--no-export-pdf",
        help="Export a PDF dossier (falls back to HTML on failure).",
    ),
    output_format: OutputFormat = typer.Option(
        OutputFormat.table,
        "--format",
        help="Terminal output format: table or json.",
    ),
    json_raw: bool = typer.Option(
        False,
        "--json-raw/--no-json-raw",
        help="(--format json) Include analysis.raw with the raw AI provider payload.",
    ),
    sherlock: bool = typer.Option(
        False,
        "--sherlock/--no-sherlock",
        help="Enable the Sherlock manifest (400+ sites, auto-downloaded to data/sherlock.json).",
    ),
    strict: bool = typer.Option(
        False,
        "--strict/--no-strict",
        help="Apply conservative heuristics to trim common false positives (handy with Sherlock).",
    ),
) -> None:
    normalized_emails = [_normalize_email(e) for e in emails] if emails else None
    categories = {c.strip().lower() for c in (category or []) if c.strip()} or None
    if nsfw == NsfwPolicy.inherit:
        no_nsfw: bool | None = None
    elif nsfw == NsfwPolicy.exclude:
        no_nsfw = True
    else:
        no_nsfw = False

    output_format = _auto_output_format(output_format)
    language = _resolve_language(spanish)
    asyncio.run(
        _hunt_async(
            usernames=usernames if usernames else None,
            emails=normalized_emails if normalized_emails else None,
            deep_analyze=ai,
            export_pdf=export_pdf,
            export_json=export_json,
            output_format=output_format,
            include_raw_in_json=json_raw,
            scan_localpart=scan_localpart,
            use_site_lists=use_site_lists,
            username_sites_path=username_sites_path,
            email_sites_path=email_sites_path,
            sites_max_concurrency=sites_max_concurrency,
            categories=categories,
            no_nsfw=no_nsfw,
            use_sherlock=sherlock,
            strict=strict,
            language=language,
        )
    )


@app.command(help="Step-by-step interactive assistant for newcomers.")
def wizard() -> None:
    console = _console
    print_banner(console)

    settings = AppSettings()
    mode = Prompt.ask(
        "What do you want to hunt?",
        choices=["username", "email", "both"],
        default="both",
    )

    usernames: list[str] | None
    emails: list[str] | None

    if mode in ("username", "both"):
        u = Prompt.ask("Comma-separated usernames", default="").strip()
        usernames = [x.strip() for x in u.split(",") if x.strip()] if u else None
    else:
        usernames = None

    if mode in ("email", "both"):
        e = Prompt.ask("Comma-separated emails", default="").strip()
        emails = [_normalize_email(x.strip()) for x in e.split(",") if x.strip()] if e else None
    else:
        emails = None

    if not usernames and not emails:
        console.print("[red]Need at least one username or email.[/red]")
        raise typer.Exit(code=2)

    default_language = settings.default_language.label().lower()
    language_choice = Prompt.ask(
        "Output language (english/spanish)",
        choices=["english", "spanish"],
        default=default_language,
    )
    language = Language.SPANISH if language_choice == "spanish" else Language.ENGLISH

    use_site_lists = Confirm.ask("Enable large site-lists engine?", default=False)
    use_sherlock = Confirm.ask("Enable Sherlock (400+ sites)?", default=False)
    strict = Confirm.ask("Strict mode (trim false positives)?", default=False)

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
    export_json = Confirm.ask("Export JSON to reports/?", default=False)
    export_pdf = Confirm.ask("Export PDF/HTML to reports/?", default=False)

    asyncio.run(
        _hunt_async(
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
        )
    )


@app.command(help="Re-run the AI profiler on a previously exported JSON dossier.")
def analyze(
    input_path: Path = typer.Argument(
        ..., exists=True, dir_okay=False, help="Path to exported JSON (reports/<target>.json)."
    ),
    output_format: OutputFormat = typer.Option(
        OutputFormat.table,
        "--format",
        help="Terminal output format: table or json.",
    ),
    spanish: bool | None = typer.Option(
        None,
        "--spanish/--english",
        "-s",
        help="Switch output language: --spanish for Spanish, --english for English (default).",
        show_default=False,
    ),
    json_raw: bool = typer.Option(
        False,
        "--json-raw/--no-json-raw",
        help="(--format json) Include analysis.raw with the raw AI provider payload.",
    ),
) -> None:
    raw = input_path.read_text(encoding="utf-8")
    person = PersonEntity.model_validate_json(raw)
    output_format = _auto_output_format(output_format)
    language = _resolve_language(spanish)
    asyncio.run(
        _analyze_async(
            person=person,
            output_format=output_format,
            emit_json=True,
            include_raw_in_json=json_raw,
            language=language,
        )
    )


def run() -> None:
    try:
        app()
    except BrokenPipeError:
        with suppress(Exception):
            sys.stdout.flush()
        with suppress(Exception):
            fd = os.open(os.devnull, os.O_WRONLY)
            os.dup2(fd, sys.stdout.fileno())
            os.close(fd)
        raise SystemExit(0)
    except OSError as exc:
        if exc.errno == errno.EPIPE:
            raise SystemExit(0)
        raise


if __name__ == "__main__":
    run()
