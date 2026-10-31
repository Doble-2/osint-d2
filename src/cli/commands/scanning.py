"""`scan`, `scan-email`, `hunt`, and `analyze`."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.markup import escape
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from adapters.ai_analyst import analyze_person
from cli.ui_components import build_analysis_panel
from core.config import AppSettings
from core.domain.language import Language
from core.domain.models import PersonEntity
from core.services.identity_pipeline import (
    HuntRequest,
    PipelineHooks,
    SiteListOptions,
    hunt as run_hunt_pipeline,
    scan_email as run_email_pipeline,
    scan_username as run_username_pipeline,
)
from cli.app import app
from cli.shared import (
    AI_PROVIDER_HELP, OutputFormat, NsfwPolicy, apply_proxy_overrides, auto_output_format, configure_ai_for_run,
    dump_person_json, err_console, normalize_email, out_console, resolve_language, split_csv,
    validate_ai_options, validate_trust,
)
from cli.output import handle_exports, print_breaches_table, print_profiles_table


async def hunt_async(
    *,
    settings: AppSettings,
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
    breach_check: bool = False,
    trust_anchors: list[str] | None = None,
) -> None:
    if not usernames and not emails:
        raise typer.BadParameter("Provide at least one username or email to hunt.")

    if breach_check and not emails:
        raise typer.BadParameter("--breach-check requires --emails/-e (you passed only usernames).")
    if breach_check and not settings.hibp_api_key:
        raise typer.BadParameter("--breach-check requires a HaveIBeenPwned API key in OSINT_D2_HIBP_API_KEY.")

    output_format = auto_output_format(output_format)
    human = output_format == OutputFormat.table
    console = out_console if human else Console(stderr=True)

    # settings se inyecta desde el comando.
    status_ctx = console.status("Building aggregated intelligence...", spinner="dots") if human else None
    progress: Progress | None = None
    progress_task_id: TaskID | None = None

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
            use_breach_check=breach_check,
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
        print_profiles_table(person=person, primary_usernames=primary_usernames)
        print_breaches_table(person=person)

    # ── Trust anchor filtering ──
    if trust_anchors:
        from core.services.trust_anchor import (
            TrustAnchor, build_reference_from_profiles, filter_profiles_by_trust,
        )
        anchors = [TrustAnchor.parse(a) for a in trust_anchors]
        ref = build_reference_from_profiles(person.profiles, anchors)
        if not ref.is_empty():
            filter_profiles_by_trust(person.profiles, ref, remove=True)
            discarded = sum(
                1 for p in person.profiles
                if isinstance(p.metadata, dict) and p.metadata.get("trust_discarded")
            )
            if discarded and human:
                console.print(
                    f"  [yellow]🛡️ Trust anchors discarded {discarded} "
                    f"false positive(s)[/yellow]\n"
                )

    if deep_analyze:
        await analyze_async(
            settings=settings,
            person=person,
            output_format=output_format,
            emit_json=False,
            include_raw_in_json=include_raw_in_json,
            language=language,
        )

    handle_exports(
        person=person,
        console=console,
        export_pdf=export_pdf,
        export_json=export_json,
        language=language,
    )

    if output_format == OutputFormat.json:
        sys.stdout.write(dump_person_json(person=person, include_raw=include_raw_in_json))
        sys.stdout.write("\n")
        sys.stdout.flush()


async def scan_async(
    *,
    settings: AppSettings,
    target: str,
    deep_analyze: bool,
    export_pdf: bool,
    export_json: bool,
    output_format: OutputFormat,
    include_raw_in_json: bool,
    language: Language,
    trust_anchors: list[str] | None = None,
) -> None:
    output_format = auto_output_format(output_format)
    human = output_format == OutputFormat.table
    console = out_console if human else Console(stderr=True)

    status_ctx = console.status("Running baseline sources...", spinner="dots") if human else None
    if status_ctx:
        status_ctx.__enter__()
    try:
        result = await run_username_pipeline(settings=settings, username=target)
    finally:
        if status_ctx:
            status_ctx.__exit__(None, None, None)

    person = result.person

    # ── Trust anchor filtering ──
    if trust_anchors:
        from core.services.trust_anchor import (
            TrustAnchor, build_reference_from_profiles, filter_profiles_by_trust,
        )
        anchors = [TrustAnchor.parse(a) for a in trust_anchors]
        ref = build_reference_from_profiles(person.profiles, anchors)
        if not ref.is_empty():
            filter_profiles_by_trust(person.profiles, ref, remove=True)
            discarded = sum(
                1 for p in person.profiles
                if isinstance(p.metadata, dict) and p.metadata.get("trust_discarded")
            )
            if discarded and human:
                console.print(
                    f"  [yellow]🛡️ Trust anchors discarded {discarded} "
                    f"false positive(s)[/yellow]\n"
                )

    if human:
        print_profiles_table(person=person, primary_usernames=[target])

    if deep_analyze:
        await analyze_async(
            settings=settings,
            person=person,
            output_format=output_format,
            emit_json=False,
            include_raw_in_json=include_raw_in_json,
            language=language,
        )

    handle_exports(
        person=person,
        console=console,
        export_pdf=export_pdf,
        export_json=export_json,
        language=language,
    )

    if output_format == OutputFormat.json:
        sys.stdout.write(dump_person_json(person=person, include_raw=include_raw_in_json))
        sys.stdout.write("\n")
        sys.stdout.flush()


async def scan_email_async(
    *,
    settings: AppSettings,
    email: str,
    deep_analyze: bool,
    export_pdf: bool,
    export_json: bool,
    output_format: OutputFormat,
    include_raw_in_json: bool,
    scan_localpart: bool,
    language: Language,
) -> None:
    output_format = auto_output_format(output_format)
    human = output_format == OutputFormat.table
    console = out_console if human else Console(stderr=True)

    status_ctx = console.status("Scanning email intelligence sources...", spinner="dots") if human else None
    if status_ctx:
        status_ctx.__enter__()
    try:
        result = await run_email_pipeline(
            settings=settings,
            email=email,
            scan_localpart=scan_localpart,
        )
    finally:
        if status_ctx:
            status_ctx.__exit__(None, None, None)

    person = result.person

    if human:
        print_profiles_table(person=person, primary_usernames=[email])

    if deep_analyze:
        await analyze_async(
            settings=settings,
            person=person,
            output_format=output_format,
            emit_json=False,
            include_raw_in_json=include_raw_in_json,
            language=language,
        )

    handle_exports(
        person=person,
        console=console,
        export_pdf=export_pdf,
        export_json=export_json,
        language=language,
    )

    if output_format == OutputFormat.json:
        sys.stdout.write(dump_person_json(person=person, include_raw=include_raw_in_json))
        sys.stdout.write("\n")
        sys.stdout.flush()


async def analyze_async(
    *,
    settings: AppSettings,
    person: PersonEntity,
    output_format: OutputFormat,
    emit_json: bool,
    include_raw_in_json: bool,
    language: Language,
) -> bool:
    """Run the profiler; returns False when it fails."""
    human = output_format == OutputFormat.table
    console = out_console if human else err_console
    succeeded = True

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
            # UX: si el proveedor rate-limitea y caemos a heurístico, explicarlo claramente.
            if getattr(report, "model", None) == "heuristic":
                reason = ""
                try:
                    reason = str((report.raw or {}).get("reason") or "")
                except Exception:
                    reason = ""
                if "provider_failed:RateLimitError" in reason or "429" in reason:
                    console.print(
                        "[yellow]The AI provider is rate-limiting requests (429).[/yellow] "
                        "Showing the local heuristic analysis instead. "
                        "Wait 30-90 seconds and retry, or try another --ai-provider."
                    )
            console.print(build_analysis_panel(report))
    except Exception as exc:
        succeeded = False
        console.print(f"\n[red]AI analysis failed:[/red] {exc}")

    if emit_json and not human:
        sys.stdout.write(dump_person_json(person=person, include_raw=include_raw_in_json))
        sys.stdout.write("\n")
        sys.stdout.flush()
    return succeeded


@app.command(help="Quick username sweep across the default intelligence sources.")
def scan(
    target: str = typer.Argument(..., help="Username or alias to investigate."),
    deep_analyze: bool = typer.Option(
        False,
        "--deep-analyze/--no-deep-analyze",
        help="Send the collected evidence to the configured AI provider for analysis.",
    ),
    ai_provider: str | None = typer.Option(
        None,
        "--ai-provider",
        help=AI_PROVIDER_HELP,
        show_default=False,
    ),
    ai_key: str | None = typer.Option(
        None,
        "--ai-key",
        help="AI API key (optional). Prefer `osint-d2 doctor setup-ai` to avoid shell history leaks.",
        show_default=False,
    ),
    ai_save: bool = typer.Option(
        False,
        "--ai-save/--no-ai-save",
        help="Persist provider configuration in the user config (.env) for next runs.",
    ),
    language: Language | None = typer.Option(
        None,
        "--language",
        "-l",
        help="Switch output language: --language [es|en|pt|ar|ru] (default: en).",
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
    output_format: OutputFormat | None = typer.Option(
        None,
        "--format",
        help="Output format: table or json. Defaults to table in a terminal and json when piped.",
        show_default=False,
    ),
    json_raw: bool = typer.Option(
        False,
        "--json-raw/--no-json-raw",
        help="(--format json) Include analysis.raw with the raw AI provider payload.",
    ),
    proxy: str | None = typer.Option(
        None,
        "--proxy",
        help="Override proxy mode: residential, datacenter (auto-detected from OSINT_D2_PROXY_API_KEY by default).",
        show_default=False,
    ),
    no_proxy: bool = typer.Option(
        False,
        "--no-proxy",
        help="Disable proxy for this run even if configured in .env.",
    ),
    proxy_country: str | None = typer.Option(
        None,
        "--proxy-country",
        help="2-letter country code for geo-targeted proxy (e.g. 'us').",
        show_default=False,
    ),
    trust: list[str] | None = typer.Option(
        None,
        "--trust",
        help="Known-good account (repeatable). Format: network:username or email:address, e.g. github:johndoe.",
        show_default=False,
    ),
) -> None:
    trust_anchors = validate_trust(trust)
    validate_ai_options(analysis=deep_analyze, ai_provider=ai_provider, ai_key=ai_key)
    output_format = auto_output_format(output_format)
    language = resolve_language(language)
    settings = apply_proxy_overrides(
        AppSettings(), proxy=proxy, no_proxy=no_proxy, proxy_country=proxy_country,
    )
    if deep_analyze and ai_provider:
        settings = configure_ai_for_run(
            settings=settings,
            ai_provider=ai_provider,
            ai_key=ai_key,
            ai_save=ai_save,
            interactive=sys.stdin.isatty() and sys.stdout.isatty(),
            console=out_console,
        )
    asyncio.run(
        scan_async(
            settings=settings,
            target=target,
            deep_analyze=deep_analyze,
            export_pdf=export_pdf,
            export_json=export_json,
            output_format=output_format,
            include_raw_in_json=json_raw,
            language=language,
            trust_anchors=trust_anchors,
        )
    )


@app.command(name="scan-email", help="Focused email pivoting across supported sources.")
def scan_email(
    email: str = typer.Argument(..., help="Target email address (e.g. user@example.com)."),
    deep_analyze: bool = typer.Option(
        False,
        "--deep-analyze/--no-deep-analyze",
        help="Send the collected evidence to the configured AI provider for analysis.",
    ),
    ai_provider: str | None = typer.Option(
        None,
        "--ai-provider",
        help=AI_PROVIDER_HELP,
        show_default=False,
    ),
    ai_key: str | None = typer.Option(
        None,
        "--ai-key",
        help="AI API key (optional). Prefer `osint-d2 doctor setup-ai` to avoid shell history leaks.",
        show_default=False,
    ),
    ai_save: bool = typer.Option(
        False,
        "--ai-save/--no-ai-save",
        help="Persist provider configuration in the user config (.env) for next runs.",
    ),
    scan_localpart: bool = typer.Option(
        False,
        "--scan-localpart/--no-scan-localpart",
        help="Also try the username derived from the local part across username sources.",
    ),
    language: Language | None = typer.Option(
        None,
        "--language",
        "-l",
        help="Switch output language: --language [es|en|pt|ar|ru] (default: en).",
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
    output_format: OutputFormat | None = typer.Option(
        None,
        "--format",
        help="Output format: table or json. Defaults to table in a terminal and json when piped.",
        show_default=False,
    ),
    json_raw: bool = typer.Option(
        False,
        "--json-raw/--no-json-raw",
        help="(--format json) Include analysis.raw with the raw AI provider payload.",
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
) -> None:
    normalized = normalize_email(email)
    validate_ai_options(analysis=deep_analyze, ai_provider=ai_provider, ai_key=ai_key)
    output_format = auto_output_format(output_format)
    language = resolve_language(language)
    settings = apply_proxy_overrides(
        AppSettings(), proxy=proxy, no_proxy=no_proxy, proxy_country=proxy_country,
    )
    if deep_analyze and ai_provider:
        settings = configure_ai_for_run(
            settings=settings,
            ai_provider=ai_provider,
            ai_key=ai_key,
            ai_save=ai_save,
            interactive=sys.stdin.isatty() and sys.stdout.isatty(),
            console=out_console,
        )
    asyncio.run(
        scan_email_async(
            settings=settings,
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
        help="Target usernames (comma-separated or repeated).",
    ),
    emails: list[str] | None = typer.Option(
        None,
        "--emails",
        "-e",
        help="Target emails (comma-separated or repeated).",
    ),
    ai: bool = typer.Option(
        False,
        "--ai/--noai",
        help="Send the collected evidence to the configured AI provider for analysis.",
    ),
    ai_provider: str | None = typer.Option(
        None,
        "--ai-provider",
        help=AI_PROVIDER_HELP,
        show_default=False,
    ),
    ai_key: str | None = typer.Option(
        None,
        "--ai-key",
        help="AI API key (optional). Prefer `osint-d2 doctor setup-ai` to avoid shell history leaks.",
        show_default=False,
    ),
    ai_save: bool = typer.Option(
        False,
        "--ai-save/--no-ai-save",
        help="Persist provider configuration in the user config (.env) for next runs.",
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
    language: Language | None = typer.Option(
        None,
        "--language",
        "-l",
        help="Switch output language: --language [es|en|pt|ar|ru] (default: en).",
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
    output_format: OutputFormat | None = typer.Option(
        None,
        "--format",
        help="Output format: table or json. Defaults to table in a terminal and json when piped.",
        show_default=False,
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
    breach_check: bool = typer.Option(
        False,
        "--breach-check/--no-breach-check",
        help="Query the official HaveIBeenPwned API for emails. Requires OSINT_D2_HIBP_API_KEY.",
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
    trust: list[str] | None = typer.Option(
        None,
        "--trust",
        help="Known-good account (repeatable). Format: network:username or email:address, e.g. github:johndoe.",
        show_default=False,
    ),
) -> None:
    trust_anchors = validate_trust(trust)
    validate_ai_options(analysis=ai, ai_provider=ai_provider, ai_key=ai_key)
    usernames = split_csv(usernames)
    normalized_emails = list(dict.fromkeys(normalize_email(e) for e in split_csv(emails)))
    categories = {c.strip().lower() for c in (category or []) if c.strip()} or None
    if nsfw == NsfwPolicy.inherit:
        no_nsfw: bool | None = None
    elif nsfw == NsfwPolicy.exclude:
        no_nsfw = True
    else:
        no_nsfw = False

    output_format = auto_output_format(output_format)
    language = resolve_language(language)
    settings = apply_proxy_overrides(
        AppSettings(), proxy=proxy, no_proxy=no_proxy, proxy_country=proxy_country,
    )
    if ai and ai_provider:
        settings = configure_ai_for_run(
            settings=settings,
            ai_provider=ai_provider,
            ai_key=ai_key,
            ai_save=ai_save,
            interactive=sys.stdin.isatty() and sys.stdout.isatty(),
            console=out_console,
        )
    asyncio.run(
        hunt_async(
            settings=settings,
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
            breach_check=breach_check,
            trust_anchors=trust_anchors,
        )
    )


@app.command(help="Re-run the AI profiler on a previously exported JSON dossier.")
def analyze(
    input_path: Path = typer.Argument(
        ..., exists=True, dir_okay=False, help="Path to exported JSON (reports/<target>.json)."
    ),
    output_format: OutputFormat | None = typer.Option(
        None,
        "--format",
        help="Output format: table or json. Defaults to table in a terminal and json when piped.",
        show_default=False,
    ),
    language: Language | None = typer.Option(
        None,
        "--language",
        "-l",
        help="Switch output language: --language [es|en|pt|ar|ru] (default: en).",
        show_default=False,
    ),
    json_raw: bool = typer.Option(
        False,
        "--json-raw/--no-json-raw",
        help="(--format json) Include analysis.raw with the raw AI provider payload.",
    ),
    ai_provider: str | None = typer.Option(
        None,
        "--ai-provider",
        help=AI_PROVIDER_HELP,
        show_default=False,
    ),
    ai_key: str | None = typer.Option(
        None,
        "--ai-key",
        help="AI API key (optional). Prefer `osint-d2 doctor setup-ai` to avoid shell history leaks.",
        show_default=False,
    ),
    ai_save: bool = typer.Option(
        False,
        "--ai-save/--no-ai-save",
        help="Persist provider configuration in the user config (.env) for next runs.",
    ),
) -> None:
    validate_ai_options(analysis=True, ai_provider=ai_provider, ai_key=ai_key)
    try:
        person = PersonEntity.model_validate_json(input_path.read_text(encoding="utf-8"))
    except (ValidationError, UnicodeDecodeError):
        err_console.print(
            f"[red]Error:[/red] {escape(str(input_path))} is not a valid OSINT-D2 dossier. "
            "Use a file created with --export-json."
        )
        raise typer.Exit(code=1)
    output_format = auto_output_format(output_format)
    language = resolve_language(language)
    settings = AppSettings()
    if ai_provider:
        settings = configure_ai_for_run(
            settings=settings,
            ai_provider=ai_provider,
            ai_key=ai_key,
            ai_save=ai_save,
            interactive=sys.stdin.isatty() and sys.stdout.isatty(),
            console=out_console,
        )
    succeeded = asyncio.run(
        analyze_async(
            settings=settings,
            person=person,
            output_format=output_format,
            emit_json=True,
            include_raw_in_json=json_raw,
            language=language,
        )
    )
    if not succeeded:
        raise typer.Exit(code=1)
