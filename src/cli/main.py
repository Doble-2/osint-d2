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
    TaskID,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from adapters.ai_analyst import analyze_person
from adapters.json_exporter import export_person_json
from adapters.report_exporter import export_person_html, export_person_pdf
from cli.doctor import app as doctor_app
from cli.ui_components import build_analysis_panel, build_breaches_table, build_profiles_table, print_banner
from core.config import AppSettings, write_user_env_vars
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


def _apply_proxy_overrides(
    settings: AppSettings,
    *,
    proxy: str | None,
    no_proxy: bool,
    proxy_country: str | None,
) -> AppSettings:
    """Apply CLI proxy overrides to settings via env vars, then reload."""
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


def _print_proxy_status(settings: AppSettings, console: Console) -> None:
    mode = settings.effective_proxy_mode
    if mode:
        country = f" ({settings.proxy_country.upper()})" if settings.proxy_country else ""
        console.print(
            f"  [bright_cyan]🔒 Proxy:[/bright_cyan] "
            f"[green]{mode}{country}[/green] via ScrapingAnt\n"
        )


AI_PROVIDER_PRESETS: dict[str, dict[str, str]] = {
    # Nota: los modelos disponibles cambian según el proveedor/plan.
    "deepseek": {"base_url": "https://api.deepseek.com", "model": "deepseek-chat"},
    # Calidad (si no está disponible, el runtime hace fallback automático a un modelo más común):
    "groq": {"base_url": "https://api.groq.com/openai/v1", "model": "llama-3.1-70b-versatile"},
    "groq-70b": {"base_url": "https://api.groq.com/openai/v1", "model": "llama-3.1-70b-versatile"},
    # Velocidad (más barato/rápido):
    "groq-fast": {"base_url": "https://api.groq.com/openai/v1", "model": "llama-3.1-8b-instant"},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1", "model": "openai/gpt-4o-mini"},
    "huggingface": {"base_url": "https://api-inference.huggingface.co/v1", "model": "meta-llama/Llama-3.1-8B-Instruct"},
    # Local (gratis, privado, requiere instalar Ollama):
    "ollama": {"base_url": "http://localhost:11434/v1", "model": "llama3"},
}


def _configure_ai_for_run(
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

    key = (ai_key or "").strip() or (settings.ai_api_key or "").strip()

    # Para proveedores locales (Ollama), la key es opcional/dummy.
    if provider == "ollama" and not key:
        key = "ollama"

    if not key and interactive:
        console.print(
            "[yellow]AI provider selected but no API key found.[/yellow] "
            "Paste it now (it will be saved for next runs)."
        )
        key = Prompt.ask("AI API key", password=True).strip()

    os.environ["OSINT_D2_AI_BASE_URL"] = base_url
    os.environ["OSINT_D2_AI_MODEL"] = model
    if key:
        os.environ["OSINT_D2_AI_API_KEY"] = key

    if ai_save and key:
        env_path = write_user_env_vars(
            {
                "OSINT_D2_AI_BASE_URL": base_url,
                "OSINT_D2_AI_MODEL": model,
                "OSINT_D2_AI_API_KEY": key,
            }
        )
        console.print(f"[green]AI config saved to:[/green] {env_path}")

    return AppSettings()

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


def _resolve_language(language: Language | None) -> Language:
    if language is not None:
        return language
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
            "YES" if profile.exists else "NO",
            str(profile.url),
            err,
        )
    _console.print(table)


def _print_breaches_table(*, person: PersonEntity) -> None:
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


def _ask_trust_anchors(console: Console) -> list[str]:
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
        "  [dim]Examples: instagram:xkissmely  email:kissmelymarcano@gmail.com[/dim]\n"
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


async def _hunt_async(
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

    output_format = _auto_output_format(output_format)
    human = output_format == OutputFormat.table
    console = _console if human else Console(stderr=True)

    if human:
        print_banner(console)

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
        _print_profiles_table(person=person, primary_usernames=primary_usernames)
        _print_breaches_table(person=person)

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
        await _analyze_async(
            settings=settings,
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
    output_format = _auto_output_format(output_format)
    human = output_format == OutputFormat.table
    console = _console if human else Console(stderr=True)

    if human:
        print_banner(console)

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
        _print_profiles_table(person=person, primary_usernames=[target])

    if deep_analyze:
        await _analyze_async(
            settings=settings,
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
            settings=settings,
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
            settings=settings,
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
    settings: AppSettings,
    person: PersonEntity,
    output_format: OutputFormat,
    emit_json: bool,
    include_raw_in_json: bool,
    language: Language,
) -> None:
    human = output_format == OutputFormat.table
    console = _console if human else Console(stderr=True)

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
            # UX: si el proveedor rate-limitea y caemos a heurístico, explicarlo claramente.
            if getattr(report, "model", None) == "heuristic":
                reason = ""
                try:
                    reason = str((report.raw or {}).get("reason") or "")
                except Exception:
                    reason = ""
                if "provider_failed:RateLimitError" in reason or "429" in reason:
                    console.print(
                        "[yellow]AI remoto rate-limited (TPM/429).[/yellow] "
                        "Mostrando análisis heurístico local. "
                        "Sugerencias: espera 30–90s y reintenta; reduce concurrencia/uso; "
                        "o usa un preset distinto (p.ej. `--ai-provider groq` para mejor calidad)."
                    )
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
    ai_provider: str | None = typer.Option(
        None,
        "--ai-provider",
        help="AI provider preset: deepseek|groq|groq-70b|groq-fast|openrouter|huggingface (prompts for key if missing).",
        show_default=False,
    ),
    ai_key: str | None = typer.Option(
        None,
        "--ai-key",
        help="AI API key (optional). Prefer `osint-d2 doctor setup-ai` to avoid shell history leaks.",
        show_default=False,
    ),
    ai_save: bool = typer.Option(
        True,
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
        help="Trusted source of truth (repeatable). Format: network:username (e.g. --trust instagram:xkissmely).",
        show_default=False,
    ),
) -> None:
    output_format = _auto_output_format(output_format)
    language = _resolve_language(language)
    settings = _apply_proxy_overrides(
        AppSettings(), proxy=proxy, no_proxy=no_proxy, proxy_country=proxy_country,
    )
    if deep_analyze and ai_provider:
        settings = _configure_ai_for_run(
            settings=settings,
            ai_provider=ai_provider,
            ai_key=ai_key,
            ai_save=ai_save,
            interactive=sys.stdin.isatty() and sys.stdout.isatty(),
            console=_console,
        )
    asyncio.run(
        _scan_async(
            settings=settings,
            target=target,
            deep_analyze=deep_analyze,
            export_pdf=export_pdf,
            export_json=export_json,
            output_format=output_format,
            include_raw_in_json=json_raw,
            language=language,
            trust_anchors=trust or [],
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
    ai_provider: str | None = typer.Option(
        None,
        "--ai-provider",
        help="AI provider preset: deepseek|groq|groq-70b|groq-fast|openrouter|huggingface (prompts for key if missing).",
        show_default=False,
    ),
    ai_key: str | None = typer.Option(
        None,
        "--ai-key",
        help="AI API key (optional). Prefer `osint-d2 doctor setup-ai` to avoid shell history leaks.",
        show_default=False,
    ),
    ai_save: bool = typer.Option(
        True,
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
    normalized = _normalize_email(email)
    output_format = _auto_output_format(output_format)
    language = _resolve_language(language)
    settings = _apply_proxy_overrides(
        AppSettings(), proxy=proxy, no_proxy=no_proxy, proxy_country=proxy_country,
    )
    if deep_analyze and ai_provider:
        settings = _configure_ai_for_run(
            settings=settings,
            ai_provider=ai_provider,
            ai_key=ai_key,
            ai_save=ai_save,
            interactive=sys.stdin.isatty() and sys.stdout.isatty(),
            console=_console,
        )
    asyncio.run(
        _scan_email_async(
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
    ai_provider: str | None = typer.Option(
        None,
        "--ai-provider",
        help="AI provider preset: deepseek|groq|groq-70b|groq-fast|openrouter|huggingface (prompts for key if missing).",
        show_default=False,
    ),
    ai_key: str | None = typer.Option(
        None,
        "--ai-key",
        help="AI API key (optional). Prefer `osint-d2 doctor setup-ai` to avoid shell history leaks.",
        show_default=False,
    ),
    ai_save: bool = typer.Option(
        True,
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
        show_default=True,
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
    breach_check: bool = typer.Option(
        False,
        "--breach-check/--no-breach-check",
        help="Query HaveIBeenPwned unifiedsearch for emails (best-effort; may be rate-limited).",
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
        help="Trusted source of truth (repeatable). Format: network:username (e.g. --trust instagram:xkissmely).",
        show_default=False,
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
    language = _resolve_language(language)
    settings = _apply_proxy_overrides(
        AppSettings(), proxy=proxy, no_proxy=no_proxy, proxy_country=proxy_country,
    )
    if ai and ai_provider:
        settings = _configure_ai_for_run(
            settings=settings,
            ai_provider=ai_provider,
            ai_key=ai_key,
            ai_save=ai_save,
            interactive=sys.stdin.isatty() and sys.stdout.isatty(),
            console=_console,
        )
    asyncio.run(
        _hunt_async(
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
            trust_anchors=trust or [],
        )
    )


@app.command(help="Autonomous OSINT investigation powered by agentic AI.")
def agent(
    objective: str = typer.Argument(
        ...,
        help="Investigation target or free-form objective (e.g. 'torvalds', 'angel@email.com').",
    ),
    ai_provider: str | None = typer.Option(
        None,
        "--ai-provider",
        help="AI provider preset: deepseek|groq|groq-70b|openrouter|huggingface.",
        show_default=False,
    ),
    ai_key: str | None = typer.Option(
        None,
        "--ai-key",
        help="AI API key (optional). Prefer `osint-d2 doctor setup-ai`.",
        show_default=False,
    ),
    ai_save: bool = typer.Option(
        True,
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
        help="Allow the agent to query HaveIBeenPwned for breaches.",
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
    trust: list[str] | None = typer.Option(
        None,
        "--trust",
        help="Trusted source of truth (repeatable). Format: network:username (e.g. --trust instagram:xkissmely --trust github:doble-2).",
        show_default=False,
    ),
) -> None:
    language = _resolve_language(language)
    settings = _apply_proxy_overrides(
        AppSettings(), proxy=proxy, no_proxy=no_proxy, proxy_country=proxy_country,
    )
    if ai_provider:
        settings = _configure_ai_for_run(
            settings=settings,
            ai_provider=ai_provider,
            ai_key=ai_key,
            ai_save=ai_save,
            interactive=sys.stdin.isatty() and sys.stdout.isatty(),
            console=_console,
        )

    if not settings.ai_api_key:
        _console.print(
            "[red]Error:[/red] Agent mode requires an AI provider. "
            "Run [bold]osint-d2 doctor setup-ai[/bold] or use --ai-provider.",
        )
        raise typer.Exit(1)

    asyncio.run(
        _agent_async(
            settings=settings,
            objective=objective,
            max_steps=max_steps,
            language=language,
            breach_check=breach_check,
            export_json=export_json,
            export_pdf=export_pdf,
            trust_anchors=trust or [],
        )
    )


async def _agent_async(
    *,
    settings: AppSettings,
    objective: str,
    max_steps: int,
    language: Language,
    breach_check: bool,
    export_json: bool,
    export_pdf: bool,
    trust_anchors: list[str] | None = None,
) -> None:
    from core.services.agent_engine import AgentEngine, AgentStep

    console = _console
    console.print()
    console.print(
        "[bold bright_cyan]╭─────────────────────────────────────────────╮[/bold bright_cyan]"
    )
    console.print(
        "[bold bright_cyan]│[/bold bright_cyan]  "
        "[bold white]OSINT-D2 Agent Mode[/bold white] 🤖"
        "                    [bold bright_cyan]│[/bold bright_cyan]"
    )
    console.print(
        f"[bold bright_cyan]│[/bold bright_cyan]  "
        f"Objective: [yellow]{objective[:38]}[/yellow]"
        f"{'…' if len(objective) > 38 else ''}"
        f"{' ' * max(0, 38 - len(objective))}"
        f"[bold bright_cyan]│[/bold bright_cyan]"
    )
    console.print(
        f"[bold bright_cyan]│[/bold bright_cyan]  "
        f"Max steps: [green]{max_steps}[/green] | "
        f"Model: [green]{settings.ai_model}[/green]"
        f"{' ' * max(0, 20 - len(settings.ai_model))}"
        f"[bold bright_cyan]│[/bold bright_cyan]"
    )
    console.print(
        "[bold bright_cyan]╰─────────────────────────────────────────────╯[/bold bright_cyan]"
    )
    console.print()

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
                    f"(confidence={confidence}, highlights={n_highlights})"
                )
            else:
                args_str = ", ".join(f'{k}="{v}"' for k, v in step.tool_args.items())
                console.print(
                    f"  🔍 [bold]Step {step.step_number}/{max_steps}:[/bold] "
                    f"[cyan]{step.tool_name}[/cyan]({args_str})"
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
            console.print(f"     [italic dim]{preview}[/italic dim]\n")

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
    else:
        console.print(
            f"  [bold yellow]⚠[/bold yellow] Agent reached max steps "
            f"({result.total_steps}/{max_steps}).\n"
        )

    # Show analysis first — it's the main deliverable in agent mode.
    if person.analysis:
        panel = build_analysis_panel(person.analysis)
        console.print(panel)

    # Show only confirmed profiles (the full table goes into the PDF).
    confirmed = [p for p in person.profiles if p.exists]
    if confirmed:
        from rich.table import Table as RichTable

        tbl = RichTable(
            title="Confirmed Profiles",
            title_style="bold bright_cyan",
            border_style="dim",
            show_lines=False,
        )
        tbl.add_column("Network", style="bold")
        tbl.add_column("Username")
        tbl.add_column("URL", style="dim")
        for p in confirmed:
            tbl.add_row(
                p.network_name,
                p.username,
                str(p.url)[:72] + ("…" if len(str(p.url)) > 72 else ""),
            )
        console.print()
        console.print(tbl)
        console.print(
            f"\n  [dim]{len(confirmed)} confirmed / "
            f"{len(person.profiles)} total scanned "
            f"(full table in PDF)[/dim]\n"
        )

    # Exports.
    _handle_exports(
        person=person,
        console=console,
        export_pdf=export_pdf,
        export_json=export_json,
        language=language,
    )


@app.command(help="Step-by-step interactive assistant for newcomers.")
def wizard() -> None:
    console = _console
    print_banner(console)

    settings = AppSettings()
    mode = Prompt.ask(
        "What do you want to hunt?",
        choices=["username", "email", "both", "agent"],
        default="both",
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
        trust_anchors = _ask_trust_anchors(console)

        export_json = Confirm.ask("Export JSON to reports/?", default=False)
        export_pdf = Confirm.ask("Export PDF/HTML to reports/?", default=False)

        # Ensure AI is configured.
        settings_now = AppSettings()
        if not (settings_now.ai_api_key or "").strip():
            console.print(
                "[yellow]Agent mode requires an AI provider.[/yellow]"
            )
            if Confirm.ask("Configure AI provider now?", default=True):
                provider = Prompt.ask(
                    "Provider",
                    choices=["groq", "groq-70b", "groq-fast", "deepseek", "openrouter", "huggingface"],
                    default="deepseek",
                ).strip().lower()

                presets: dict[str, dict[str, str]] = {
                    "deepseek": {"OSINT_D2_AI_BASE_URL": "https://api.deepseek.com", "OSINT_D2_AI_MODEL": "deepseek-chat"},
                    "groq": {"OSINT_D2_AI_BASE_URL": "https://api.groq.com/openai/v1", "OSINT_D2_AI_MODEL": "llama-3.1-70b-versatile"},
                    "groq-70b": {"OSINT_D2_AI_BASE_URL": "https://api.groq.com/openai/v1", "OSINT_D2_AI_MODEL": "llama-3.1-70b-versatile"},
                    "groq-fast": {"OSINT_D2_AI_BASE_URL": "https://api.groq.com/openai/v1", "OSINT_D2_AI_MODEL": "llama-3.1-8b-instant"},
                    "openrouter": {"OSINT_D2_AI_BASE_URL": "https://openrouter.ai/api/v1", "OSINT_D2_AI_MODEL": "openai/gpt-4o-mini"},
                    "huggingface": {"OSINT_D2_AI_BASE_URL": "https://api-inference.huggingface.co/v1", "OSINT_D2_AI_MODEL": "meta-llama/Llama-3.1-8B-Instruct"},
                }
                preset = presets.get(provider, {})
                base_url = Prompt.ask("AI base URL", default=preset.get("OSINT_D2_AI_BASE_URL", "")).strip()
                model = Prompt.ask("AI model", default=preset.get("OSINT_D2_AI_MODEL", "")).strip()
                api_key = Prompt.ask("AI API key", password=True).strip()

                if base_url and model and api_key:
                    env_path = write_user_env_vars({
                        "OSINT_D2_AI_BASE_URL": base_url,
                        "OSINT_D2_AI_MODEL": model,
                        "OSINT_D2_AI_API_KEY": api_key,
                    })
                    _console.print(f"[green]AI config saved to:[/green] {env_path}")
                else:
                    console.print("[red]AI provider is required for agent mode.[/red]")
                    raise typer.Exit(code=2)

        final_settings = _apply_proxy_overrides(
            AppSettings(),
            proxy=proxy_mode,
            no_proxy=False,
            proxy_country=proxy_country,
        )

        asyncio.run(
            _agent_async(
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
        emails = [_normalize_email(x.strip()) for x in e.split(",") if x.strip()] if e else None
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
        if not (settings_now.ai_api_key or "").strip() and settings_now.ai_base_url.startswith("https://api.deepseek"):
            if Confirm.ask("No AI key configured. Configure a free-tier provider now (recommended)?", default=True):
                provider = Prompt.ask(
                    "Provider",
                    choices=["groq", "groq-70b", "groq-fast", "deepseek", "openrouter", "huggingface"],
                    default="groq",
                ).strip().lower()

                presets_classic: dict[str, dict[str, str]] = {
                    "deepseek": {"OSINT_D2_AI_BASE_URL": "https://api.deepseek.com", "OSINT_D2_AI_MODEL": "deepseek-chat"},
                    "groq": {"OSINT_D2_AI_BASE_URL": "https://api.groq.com/openai/v1", "OSINT_D2_AI_MODEL": "llama-3.1-70b-versatile"},
                    "groq-70b": {"OSINT_D2_AI_BASE_URL": "https://api.groq.com/openai/v1", "OSINT_D2_AI_MODEL": "llama-3.1-70b-versatile"},
                    "groq-fast": {"OSINT_D2_AI_BASE_URL": "https://api.groq.com/openai/v1", "OSINT_D2_AI_MODEL": "llama-3.1-8b-instant"},
                    "openrouter": {"OSINT_D2_AI_BASE_URL": "https://openrouter.ai/api/v1", "OSINT_D2_AI_MODEL": "openai/gpt-4o-mini"},
                    "huggingface": {"OSINT_D2_AI_BASE_URL": "https://api-inference.huggingface.co/v1", "OSINT_D2_AI_MODEL": "meta-llama/Llama-3.1-8B-Instruct"},
                }
                preset = presets_classic.get(provider, {})
                base_url = Prompt.ask("AI base URL", default=preset.get("OSINT_D2_AI_BASE_URL", "")).strip()
                model = Prompt.ask("AI model", default=preset.get("OSINT_D2_AI_MODEL", "")).strip()
                api_key = Prompt.ask("AI API key", password=True).strip()

                if base_url and model and api_key:
                    env_path = write_user_env_vars(
                        {
                            "OSINT_D2_AI_BASE_URL": base_url,
                            "OSINT_D2_AI_MODEL": model,
                            "OSINT_D2_AI_API_KEY": api_key,
                        }
                    )
                    _console.print(f"[green]AI config saved to:[/green] {env_path}")
                else:
                    _console.print("[yellow]Skipping remote AI setup; using heuristic fallback.[/yellow]")
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
    wiz_trust_anchors = _ask_trust_anchors(console)


    wiz_final_settings = _apply_proxy_overrides(
        AppSettings(),
        proxy=wiz_proxy_mode,
        no_proxy=False,
        proxy_country=wiz_proxy_country,
    )

    asyncio.run(
        _hunt_async(
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
        help="AI provider preset: deepseek|groq|groq-70b|groq-fast|openrouter|huggingface (prompts for key if missing).",
        show_default=False,
    ),
    ai_key: str | None = typer.Option(
        None,
        "--ai-key",
        help="AI API key (optional). Prefer `osint-d2 doctor setup-ai` to avoid shell history leaks.",
        show_default=False,
    ),
    ai_save: bool = typer.Option(
        True,
        "--ai-save/--no-ai-save",
        help="Persist provider configuration in the user config (.env) for next runs.",
    ),
) -> None:
    raw = input_path.read_text(encoding="utf-8")
    person = PersonEntity.model_validate_json(raw)
    output_format = _auto_output_format(output_format)
    language = _resolve_language(language)
    settings = AppSettings()
    if ai_provider:
        settings = _configure_ai_for_run(
            settings=settings,
            ai_provider=ai_provider,
            ai_key=ai_key,
            ai_save=ai_save,
            interactive=sys.stdin.isatty() and sys.stdout.isatty(),
            console=_console,
        )
    asyncio.run(
        _analyze_async(
            settings=settings,
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
