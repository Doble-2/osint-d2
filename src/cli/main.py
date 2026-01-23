"""Entrada CLI (Typer + Rich).

Por qué Typer + Rich:
- Typer (Click) permite una UX de CLI moderna con autocompletado y ayuda clara.
- Rich mejora la legibilidad: paneles, tablas, spinners y estilos consistentes.

Nota de arquitectura:
- Esta capa *orquesta*; no contiene scraping ni lógica de negocio.
- Cualquier operación con I/O se encapsula en funciones async y se ejecuta desde
  el comando con `asyncio.run(...)` para mantener compatibilidad con Typer.
"""

from __future__ import annotations

import asyncio
import errno
import json
import os
from enum import Enum
import sys
from pathlib import Path
import signal
from contextlib import suppress
from typing import Iterable

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
from adapters.email_sources import (
    GravatarProfileScanner,
    GravatarScanner,
    OpenPGPKeysScanner,
    UbuntuKeyserverScanner,
)
from adapters.json_exporter import export_person_json
from adapters.osint_sources import (
    AboutMeScanner,
    BehanceScanner,
    DevToScanner,
    DribbbleScanner,
    GitHubGistScanner,
    GitHubScanner,
    GitLabScanner,
    KaggleScanner,
    KeybaseScanner,
    MediumScanner,
    NpmScanner,
    PinterestScanner,
    ProductHuntScanner,
    RedditScanner,
    SoundCloudScanner,
    TelegramScanner,
    TwitchScanner,
    XScanner,
)
from adapters.profile_enricher import enrich_profiles_from_html
from adapters.report_exporter import export_person_html, export_person_pdf
from adapters.site_lists import load_email_sites, load_username_sites, run_email_sites, run_username_sites
from adapters.sherlock_runner import run_sherlock_username
from cli.doctor import app as doctor_app
from cli.ui_components import build_analysis_panel, build_profiles_table, print_banner
from core.config import AppSettings
from core.resources_loader import get_default_list_path, load_sherlock_data
from core.domain.models import SocialProfile
from core.domain.models import PersonEntity

app = typer.Typer(
    name="osint-d2",
    no_args_is_help=False,
    help="OSINT-D2: herramienta OSINT moderna para investigación de identidades.",
)

app.add_typer(doctor_app, name="doctor")

_console = Console()

# Evita ruido cuando la salida se pipea (p.ej. `| head`) en Unix.
try:
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
except Exception:
    pass


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """Punto de entrada de la app.

    Nota:
    - No imprimimos banner aquí para no ensuciar stdout en `--format json`.
    - Cada comando decide si muestra UI interactiva.
    """

    if ctx.invoked_subcommand is None:
        # UX por defecto: wizard interactivo.
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
    # Si el usuario está pipeando stdout, la UI humana (banner/tablas/paneles)
    # se trunca (p.ej. con `head`) y parece "roto". En ese caso emitimos JSON.
    if output_format == OutputFormat.table and not sys.stdout.isatty():
        Console(stderr=True).print(
            "[yellow]stdout no es TTY; usando --format json automáticamente. "
            "Usa --format table para forzarlo.[/yellow]"
        )
        return OutputFormat.json
    return output_format


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
        raise typer.BadParameter("Email inválido: falta '@'.")
    local, _, domain = email.partition("@")
    if not local or not domain or "." not in domain:
        raise typer.BadParameter("Email inválido.")
    return email


def _sanitize_target_for_filename(value: str) -> str:
    # Mantiene nombres de reporte seguros (evita '/', espacios, etc.).
    out: list[str] = []
    for ch in value.strip():
        if ch.isalnum() or ch in ("-", "_", "."):
            out.append(ch)
        elif ch in ("@", "+"):
            out.append("_")
        else:
            out.append("-")
    cleaned = "".join(out).strip("-_")
    return cleaned or "target"


def _dedupe_profiles(profiles: Iterable[SocialProfile]) -> list[SocialProfile]:
    seen: set[tuple[str, str, str]] = set()
    out: list[SocialProfile] = []
    for p in profiles:
        key = (p.network_name, p.username, str(p.url))
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


_STRICT_SHERLOCK_DENYLIST: set[str] = {
    # Sitios típicos con falsos positivos por devolver páginas genéricas.
    "avizo",
    "fanpop",
    "hubski",
}

_STRICT_SUSPICIOUS_URL_PARTS: tuple[str, ...] = (
    "login",
    "sign_in",
    "consent",
    "privacy",
    "cookie",
    "redirect",
    "return_url=",
    "callbackurl=",
    "search?",
    "search/?",
    "vendor_not_found",
    "nastaveni-souhlasu",
)


def _strict_keep_profile(*, profile: SocialProfile, username: str) -> bool:
    """Filtro conservador para reducir falsos positivos en resultados tipo Sherlock.

    Heurística:
    - Solo aplica cuando `metadata.source == 'sherlock'`.
    - Excluye sitios conocidos por falsos positivos.
    - Excluye URLs finales que parecen login/consent/búsqueda.
    - Exige que el username aparezca en la URL o en el title/description.
    """

    if not profile.existe:
        return False

    md = profile.metadata if isinstance(profile.metadata, dict) else {}
    if md.get("source") != "sherlock":
        return True

    if profile.network_name in _STRICT_SHERLOCK_DENYLIST:
        return False

    final_url = str(md.get("final_url") or profile.url)
    final_url_l = final_url.lower()
    if any(p in final_url_l for p in _STRICT_SUSPICIOUS_URL_PARTS):
        return False

    username_l = username.lower()
    if username_l in final_url_l:
        return True

    title = md.get("title")
    if isinstance(title, str) and username_l in title.lower():
        return True

    desc = md.get("meta_description")
    if isinstance(desc, str) and username_l in desc.lower():
        return True

    return False


async def _hunt_async(
    *,
    username: str | None,
    email: str | None,
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
) -> None:
    if not username and not email:
        raise typer.BadParameter("Debes indicar --username y/o --email.")

    output_format = _auto_output_format(output_format)
    human = output_format == OutputFormat.table
    console = _console if human else Console(stderr=True)

    if human:
        print_banner(console)

    settings = AppSettings()
    max_concurrency = sites_max_concurrency or settings.sites_max_concurrency
    no_nsfw_effective = settings.sites_no_nsfw if no_nsfw is None else no_nsfw

    profiles: list[SocialProfile] = []

    if human:
        status_ctx = console.status("Ejecutando búsqueda (username/email)...", spinner="dots")
        status_ctx.__enter__()
    else:
        status_ctx = None
    try:
        async def safe_scan(scanner: object, value: str, *, derived_from: str | None = None) -> SocialProfile:
            name = scanner.__class__.__name__
            network = name.removesuffix("Scanner").lower()
            try:
                prof = await scanner.scan(value)  # type: ignore[attr-defined]
                if derived_from and isinstance(prof.metadata, dict):
                    prof.metadata = {**prof.metadata, "derived_from": derived_from}

                # Parche rápido: evita URLs placeholder en X.
                if isinstance(prof.url, str) and "example.invalid/x/" in prof.url:
                    prof.url = prof.url.replace("example.invalid/x/", "x.com/")
                return prof
            except Exception as exc:
                # Si falla la request, devuelve igual una URL canónica útil.
                fallback_url = f"https://{network}.com/{value}"
                if network == "x":
                    fallback_url = f"https://x.com/{value}"
                return SocialProfile(
                    url=fallback_url,
                    username=value,
                    network_name=network,
                    existe=False,
                    metadata={"error": str(exc), "scanner": name, "derived_from": derived_from}
                    if derived_from
                    else {"error": str(exc), "scanner": name},
                )

        if username:
            username_scanners: list[object] = [
                GitHubScanner(),
                GitHubGistScanner(),
                GitLabScanner(),
                KeybaseScanner(),
                DevToScanner(),
                MediumScanner(),
                NpmScanner(),
                ProductHuntScanner(),
                RedditScanner(),
                TwitchScanner(),
                TelegramScanner(),
                AboutMeScanner(),
                PinterestScanner(),
                SoundCloudScanner(),
                KaggleScanner(),
                DribbbleScanner(),
                BehanceScanner(),
                XScanner(),
            ]
            profiles.extend(await asyncio.gather(*(safe_scan(s, username) for s in username_scanners)))

        if email:
            email_scanners: list[object] = [
                GravatarScanner(),
                GravatarProfileScanner(),
                OpenPGPKeysScanner(),
                UbuntuKeyserverScanner(),
            ]
            profiles.extend(await asyncio.gather(*(safe_scan(s, email) for s in email_scanners)))

            if scan_localpart:
                localpart = email.split("@", 1)[0]
                username_scanners2: list[object] = [
                    GitHubScanner(),
                    GitHubGistScanner(),
                    GitLabScanner(),
                    KeybaseScanner(),
                    DevToScanner(),
                    MediumScanner(),
                    NpmScanner(),
                    ProductHuntScanner(),
                    RedditScanner(),
                    TwitchScanner(),
                    TelegramScanner(),
                    AboutMeScanner(),
                    PinterestScanner(),
                    SoundCloudScanner(),
                    KaggleScanner(),
                    DribbbleScanner(),
                    BehanceScanner(),
                    XScanner(),
                ]
                profiles.extend(
                    await asyncio.gather(*(safe_scan(s, localpart, derived_from="email_localpart") for s in username_scanners2))
                )

        if use_site_lists:
            if username:
                p = username_sites_path or settings.username_sites_path
                if p and not p.exists():
                    # Si el usuario pasó solo un nombre, intentamos ubicarlo.
                    fallback = get_default_list_path(p.name)
                    if fallback:
                        p = fallback
                if p and p.exists():
                    sites_file = load_username_sites(p)
                    profiles.extend(
                        await run_username_sites(
                            username=username,
                            sites=sites_file.sites,
                            settings=settings,
                            max_concurrency=max_concurrency,
                            categories=categories,
                            no_nsfw=no_nsfw_effective,
                        )
                    )
                else:
                    if not use_sherlock:
                        console.print("[yellow]Site-lists username no configuradas (falta ruta).[/yellow]")

            if email:
                p = email_sites_path or settings.email_sites_path
                if p and not p.exists():
                    fallback = get_default_list_path(p.name)
                    if fallback:
                        p = fallback
                if p and p.exists():
                    sites_file = load_email_sites(p)
                    profiles.extend(
                        await run_email_sites(
                            email=email,
                            sites=sites_file.sites,
                            settings=settings,
                            max_concurrency=max_concurrency,
                            categories=categories,
                            no_nsfw=no_nsfw_effective,
                        )
                    )
                else:
                    if not use_sherlock:
                        console.print("[yellow]Site-lists email no configuradas (falta ruta).[/yellow]")

        # Importante: `console.status()` usa Live internamente. Si vamos a mostrar
        # una barra de progreso (también Live), debemos cerrar el status primero.
        if human and status_ctx and use_sherlock and username:
            status_ctx.__exit__(None, None, None)
            status_ctx = None

        if use_sherlock and username:
            # Sherlock: descarga a data/sherlock.json si falta.
            manifest = load_sherlock_data(refresh=False)
            if human:
                # Pre-cuenta rápida (para barra): replica el filtro NSFW básico.
                total = 0
                for site_name, info in manifest.items():
                    if site_name == "$schema":
                        continue
                    if not isinstance(info, dict):
                        continue
                    if no_nsfw_effective and bool(info.get("isNSFW")):
                        continue
                    total += 1

                progress = Progress(
                    SpinnerColumn(),
                    TextColumn("[cyan]Sherlock[/cyan] {task.completed}/{task.total} ({task.percentage:>3.0f}%)"),
                    BarColumn(bar_width=None),
                    TimeElapsedColumn(),
                    TimeRemainingColumn(),
                    console=console,
                    transient=True,
                )
                with progress:
                    task_id = progress.add_task("Sherlock", total=total)

                    def _cb(done: int, tot: int, _site: str) -> None:
                        # tot puede diferir si cambia el manifest; usamos la primera.
                        progress.update(task_id, completed=done)

                    profiles.extend(
                        await run_sherlock_username(
                            username=username,
                            manifest=manifest,
                            settings=settings,
                            max_concurrency=max_concurrency,
                            no_nsfw=no_nsfw_effective,
                            progress_callback=_cb,
                        )
                    )
            else:
                profiles.extend(
                    await run_sherlock_username(
                        username=username,
                        manifest=manifest,
                        settings=settings,
                        max_concurrency=max_concurrency,
                        no_nsfw=no_nsfw_effective,
                        progress_callback=None,
                    )
                )
    finally:
        if status_ctx:
            status_ctx.__exit__(None, None, None)

    profiles = _dedupe_profiles(profiles)

    if strict and username:
        profiles = [p for p in profiles if _strict_keep_profile(profile=p, username=username)]

    # Enriquecimiento HTML (fallback): añade metadata (title/description/og:image) útil para análisis.
    # Se ejecuta antes del análisis IA para aportar contexto adicional.
    await enrich_profiles_from_html(profiles=profiles, settings=settings, max_concurrency=min(20, max_concurrency))

    target_label = "/".join([v for v in [username, email] if v])
    person = PersonEntity(target=target_label, profiles=profiles)

    if human:
        table = build_profiles_table()
        for profile in person.profiles:
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

    if deep_analyze:
        await _analyze_async(
            person=person,
            output_format=output_format,
            emit_json=False,
            include_raw_in_json=include_raw_in_json,
        )

    safe_name = _sanitize_target_for_filename(target_label)
    if export_pdf:
        try:
            out_path = Path("reports") / f"{safe_name}.pdf"
            export_person_pdf(person=person, output_path=out_path)
            console.print(f"\n[green]PDF creado:[/green] {out_path}")
        except Exception as exc:
            console.print(f"\n[red]Error PDF:[/red] {exc}")
            html_path = Path("reports") / f"{safe_name}.html"
            export_person_html(person=person, output_path=html_path)
            console.print(f"[yellow]Fallback HTML creado:[/yellow] {html_path}")

    if export_json:
        try:
            json_path = Path("reports") / f"{safe_name}.json"
            export_person_json(person=person, output_path=json_path)
            console.print(f"\n[green]JSON creado:[/green] {json_path}")
        except Exception as exc:
            console.print(f"\n[red]Error JSON:[/red] {exc}")

    if output_format == OutputFormat.json:
        sys.stdout.write(_dump_person_json(person=person, include_raw=include_raw_in_json))
        sys.stdout.write("\n")
        sys.stdout.flush()


async def _scan_email_async(
    email: str,
    deep_analyze: bool,
    export_pdf: bool,
    export_json: bool,
    output_format: OutputFormat,
    include_raw_in_json: bool,
    scan_localpart: bool,
) -> None:
    human = output_format == OutputFormat.table
    console = _console if human else Console(stderr=True)

    if human:
        print_banner(console)

    if human:
        status_ctx = console.status("Escaneando fuentes (email)...", spinner="dots")
    else:
        status_ctx = None

    if status_ctx:
        status_ctx.__enter__()
    try:
        scanners: list[object] = [
            GravatarScanner(),
            GravatarProfileScanner(),
            OpenPGPKeysScanner(),
            UbuntuKeyserverScanner(),
        ]

        async def safe_scan(scanner: object, value: str, *, derived_from: str | None = None) -> SocialProfile:
            name = scanner.__class__.__name__
            network = name.removesuffix("Scanner").lower()
            try:
                prof = await scanner.scan(value)  # type: ignore[attr-defined]
                if derived_from and isinstance(prof.metadata, dict):
                    prof.metadata = {**prof.metadata, "derived_from": derived_from}
                return prof
            except Exception as exc:
                return SocialProfile(
                    url=f"https://example.invalid/{network}/{value}",
                    username=value,
                    network_name=network,
                    existe=False,
                    metadata={"error": str(exc), "scanner": name, "derived_from": derived_from}
                    if derived_from
                    else {"error": str(exc), "scanner": name},
                )

        profiles: list[SocialProfile] = []
        profiles.extend(await asyncio.gather(*(safe_scan(s, email) for s in scanners)))

        if scan_localpart:
            localpart = email.split("@", 1)[0]
            username_scanners: list[object] = [
                GitHubScanner(),
                GitHubGistScanner(),
                GitLabScanner(),
                KeybaseScanner(),
                DevToScanner(),
                MediumScanner(),
                NpmScanner(),
                ProductHuntScanner(),
                RedditScanner(),
                TwitchScanner(),
                TelegramScanner(),
                AboutMeScanner(),
                PinterestScanner(),
                SoundCloudScanner(),
                KaggleScanner(),
                DribbbleScanner(),
                BehanceScanner(),
                XScanner(),
            ]
            derived_profiles = await asyncio.gather(
                *(safe_scan(s, localpart, derived_from="email_localpart") for s in username_scanners)
            )
            profiles.extend(list(derived_profiles))
    finally:
        if status_ctx:
            status_ctx.__exit__(None, None, None)

    person = PersonEntity(target=email, profiles=profiles)

    if human:
        table = build_profiles_table()
        for profile in person.profiles:
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

    if deep_analyze:
        await _analyze_async(
            person=person,
            output_format=output_format,
            emit_json=False,
            include_raw_in_json=include_raw_in_json,
        )

    safe_name = _sanitize_target_for_filename(email)
    if export_pdf:
        try:
            out_path = Path("reports") / f"{safe_name}.pdf"
            export_person_pdf(person=person, output_path=out_path)
            console.print(f"\n[green]PDF creado:[/green] {out_path}")
        except Exception as exc:
            console.print(f"\n[red]Error PDF:[/red] {exc}")
            html_path = Path("reports") / f"{safe_name}.html"
            export_person_html(person=person, output_path=html_path)
            console.print(f"[yellow]Fallback HTML creado:[/yellow] {html_path}")

    if export_json:
        try:
            json_path = Path("reports") / f"{safe_name}.json"
            export_person_json(person=person, output_path=json_path)
            console.print(f"\n[green]JSON creado:[/green] {json_path}")
        except Exception as exc:
            console.print(f"\n[red]Error JSON:[/red] {exc}")

    if output_format == OutputFormat.json:
        sys.stdout.write(_dump_person_json(person=person, include_raw=include_raw_in_json))
        sys.stdout.write("\n")
        sys.stdout.flush()


async def _analyze_async(
    person: PersonEntity,
    output_format: OutputFormat,
    *,
    emit_json: bool,
    include_raw_in_json: bool,
) -> None:
    human = output_format == OutputFormat.table
    console = _console if human else Console(stderr=True)

    settings = AppSettings()
    if human:
        print_banner(console)

    try:
        if human:
            status = console.status("Analizando con IA (DeepSeek)...", spinner="dots")
            status.__enter__()
        else:
            status = None
        try:
            report = await analyze_person(person=person, settings=settings)
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
        console.print(f"\n[red]Error IA:[/red] {exc}")


async def _scan_async(
    target: str,
    deep_analyze: bool,
    export_pdf: bool,
    export_json: bool,
    output_format: OutputFormat,
    include_raw_in_json: bool,
) -> None:
    """Orquestador async del comando `scan`.

    Por qué existe:
    - Mantiene el comando Typer síncrono, pero el flujo interno preparado para
      I/O asíncrono (httpx, IA, exportación).
    """

    human = output_format == OutputFormat.table
    console = _console if human else Console(stderr=True)

    if human:
        print_banner(console)

    if human:
        status_ctx = console.status("Escaneando fuentes (mínimo viable)...", spinner="dots")
    else:
        status_ctx = None

    if status_ctx:
        status_ctx.__enter__()
    try:
        scanners = [
            GitHubScanner(),
            GitHubGistScanner(),
            GitLabScanner(),
            KeybaseScanner(),
            DevToScanner(),
            MediumScanner(),
            NpmScanner(),
            ProductHuntScanner(),
            RedditScanner(),
            TwitchScanner(),
            TelegramScanner(),
            AboutMeScanner(),
            PinterestScanner(),
            SoundCloudScanner(),
            KaggleScanner(),
            DribbbleScanner(),
            BehanceScanner(),
            XScanner(),
        ]

        async def safe_scan(scanner: object) -> SocialProfile:
            name = scanner.__class__.__name__
            network = name.removesuffix("Scanner").lower()
            try:
                # Typing: los scanners cumplen el Protocol.
                return await scanner.scan(target)  # type: ignore[attr-defined]
            except Exception as exc:
                # Nunca hacemos fallar el comando por una sola fuente.
                return SocialProfile(
                    url=f"https://example.invalid/{network}/{target}",
                    username=target,
                    network_name=network,
                    existe=False,
                    metadata={"error": str(exc), "scanner": name},
                )

        results = await asyncio.gather(*(safe_scan(s) for s in scanners), return_exceptions=False)
        profiles = list(results)
    finally:
        if status_ctx:
            status_ctx.__exit__(None, None, None)

    person = PersonEntity(target=target, profiles=list(profiles))

    if human:
        table = build_profiles_table()
        for profile in person.profiles:
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

    if deep_analyze:
        settings = AppSettings()
        try:
            if human:
                status2 = console.status("Analizando con IA (DeepSeek)...", spinner="dots")
                status2.__enter__()
            else:
                status2 = None
            try:
                report = await analyze_person(person=person, settings=settings)
                person.analysis = report
            finally:
                if status2:
                    status2.__exit__(None, None, None)

            if human:
                console.print(build_analysis_panel(report))
        except Exception as exc:
            console.print(f"\n[red]Error IA:[/red] {exc}")
    if export_pdf:
        try:
            out_path = Path("reports") / f"{person.target}.pdf"
            if human:
                status3 = console.status(f"Generando PDF: {out_path}...", spinner="dots")
                status3.__enter__()
            else:
                status3 = None
            try:
                export_person_pdf(person=person, output_path=out_path)
            finally:
                if status3:
                    status3.__exit__(None, None, None)
            console.print(f"\n[green]PDF creado:[/green] {out_path}")
        except Exception as exc:
            console.print(f"\n[red]Error PDF:[/red] {exc}")
            html_path = Path("reports") / f"{person.target}.html"
            if human:
                status4 = console.status(f"Fallback: generando HTML: {html_path}...", spinner="dots")
                status4.__enter__()
            else:
                status4 = None
            try:
                export_person_html(person=person, output_path=html_path)
            finally:
                if status4:
                    status4.__exit__(None, None, None)
            console.print(f"[yellow]Fallback HTML creado:[/yellow] {html_path}")

    if export_json:
        try:
            json_path = Path("reports") / f"{person.target}.json"
            if human:
                status5 = console.status(f"Generando JSON: {json_path}...", spinner="dots")
                status5.__enter__()
            else:
                status5 = None
            try:
                export_person_json(person=person, output_path=json_path)
            finally:
                if status5:
                    status5.__exit__(None, None, None)
            console.print(f"\n[green]JSON creado:[/green] {json_path}")
        except Exception as exc:
            console.print(f"\n[red]Error JSON:[/red] {exc}")

    if output_format == OutputFormat.json:
        # Salida estable para pipelines.
        sys.stdout.write(_dump_person_json(person=person, include_raw=include_raw_in_json))
        sys.stdout.write("\n")
        sys.stdout.flush()


@app.command()
def scan(
    target: str = typer.Argument(..., help="Username/alias objetivo a investigar."),
    deep_analyze: bool = typer.Option(
        False,
        "--deep-analyze/--no-deep-analyze",
        help="Ejecuta análisis cognitivo con IA (DeepSeek) sobre las evidencias.",
    ),
    export_pdf: bool = typer.Option(
        False,
        "--export-pdf/--no-export-pdf",
        help="Exporta un reporte PDF/HTML (dossier) en reports/.",
    ),
    export_json: bool = typer.Option(
        False,
        "--export-json/--no-export-json",
        help="Exporta el agregado (perfiles + análisis) a JSON en reports/.",
    ),
    output_format: OutputFormat = typer.Option(
        OutputFormat.table,
        "--format",
        help="Formato de salida en terminal: table|json.",
    ),
    json_raw: bool = typer.Option(
        False,
        "--json-raw/--no-json-raw",
        help="(Solo --format json) Incluir `analysis.raw` (respuesta completa del proveedor IA).",
    ),
) -> None:
    """Escanea múltiples fuentes OSINT para un target.

    Diseño:
    - En futuras iteraciones, este comando ensamblará scanners (adapters) y
      producirá un `PersonEntity` normalizado.
    """

    output_format = _auto_output_format(output_format)
    asyncio.run(
        _scan_async(
            target=target,
            deep_analyze=deep_analyze,
            export_pdf=export_pdf,
            export_json=export_json,
            output_format=output_format,
            include_raw_in_json=json_raw,
        )
    )


@app.command(name="scan-email")
def scan_email(
    email: str = typer.Argument(..., help="Email objetivo (p.ej. usuario@dominio.com)."),
    deep_analyze: bool = typer.Option(
        True,
        "--deep-analyze/--no-deep-analyze",
        help="Ejecuta análisis cognitivo con IA (DeepSeek) sobre las evidencias.",
    ),
    scan_localpart: bool = typer.Option(
        False,
        "--scan-localpart/--no-scan-localpart",
        help="También intenta el username derivado (parte antes de '@') en redes de username.",
    ),
    export_json: bool = typer.Option(
        False,
        "--export-json/--no-export-json",
        help="Exporta el agregado (perfiles + análisis) a JSON en reports/.",
    ),
    export_pdf: bool = typer.Option(
        False,
        "--export-pdf/--no-export-pdf",
        help="Exporta un reporte PDF (si falla, hace fallback a HTML).",
    ),
    output_format: OutputFormat = typer.Option(
        OutputFormat.table,
        "--format",
        help="Formato de salida en terminal: table|json.",
    ),
    json_raw: bool = typer.Option(
        False,
        "--json-raw/--no-json-raw",
        help="(Solo --format json) Incluir `analysis.raw` (respuesta completa del proveedor IA).",
    ),
) -> None:
    """OSINT orientado a email (MVP) + análisis IA."""

    normalized = _normalize_email(email)

    output_format = _auto_output_format(output_format)
    asyncio.run(
        _scan_email_async(
            email=normalized,
            deep_analyze=deep_analyze,
            export_pdf=export_pdf,
            export_json=export_json,
            output_format=output_format,
            include_raw_in_json=json_raw,
            scan_localpart=scan_localpart,
        )
    )


@app.command()
def hunt(
    username: str | None = typer.Option(
        None,
        "--username",
        "-u",
        help="Username/alias objetivo.",
    ),
    email: str | None = typer.Option(
        None,
        "--email",
        "-e",
        help="Email objetivo.",
    ),
    deep_analyze: bool = typer.Option(
        True,
        "--deep-analyze/--no-deep-analyze",
        help="Ejecuta análisis cognitivo con IA (DeepSeek) sobre las evidencias.",
    ),
    scan_localpart: bool = typer.Option(
        True,
        "--scan-localpart/--no-scan-localpart",
        help="Si hay email, también intenta el username derivado (parte antes de '@') en fuentes de username.",
    ),
    use_site_lists: bool = typer.Option(
        False,
        "--site-lists/--no-site-lists",
        help="Activa el motor data-driven (listas masivas tipo WhatsMyName/email-data).",
    ),
    username_sites_path: Path | None = typer.Option(
        None,
        "--username-sites-path",
        help="Ruta local a JSON de sitios para username (wmn-data.json).",
    ),
    email_sites_path: Path | None = typer.Option(
        None,
        "--email-sites-path",
        help="Ruta local a JSON de sitios para email (email-data.json).",
    ),
    sites_max_concurrency: int | None = typer.Option(
        None,
        "--sites-max-concurrency",
        min=1,
        max=500,
        help="Concurrencia para site-lists (si no se indica, usa OSINT_D2_SITES_MAX_CONCURRENCY).",
    ),
    category: list[str] | None = typer.Option(
        None,
        "--category",
        help="Filtra site-lists por categoría (repetible).",
    ),
    nsfw: NsfwPolicy = typer.Option(
        NsfwPolicy.inherit,
        "--nsfw",
        help="Política NSFW para site-lists: inherit|exclude|allow.",
    ),
    export_json: bool = typer.Option(
        False,
        "--export-json/--no-export-json",
        help="Exporta el agregado (perfiles + análisis) a JSON en reports/.",
    ),
    export_pdf: bool = typer.Option(
        False,
        "--export-pdf/--no-export-pdf",
        help="Exporta un reporte PDF (si falla, hace fallback a HTML).",
    ),
    output_format: OutputFormat = typer.Option(
        OutputFormat.table,
        "--format",
        help="Formato de salida en terminal: table|json.",
    ),
    json_raw: bool = typer.Option(
        False,
        "--json-raw/--no-json-raw",
        help="(Solo --format json) Incluir `analysis.raw` (respuesta completa del proveedor IA).",
    ),
    sherlock: bool = typer.Option(
        False,
        "--sherlock/--no-sherlock",
        help="Activa el manifest de Sherlock (400+ sitios, descarga automática a data/sherlock.json).",
    ),
    strict: bool = typer.Option(
        False,
        "--strict/--no-strict",
        help="Filtra falsos positivos comunes (heurística conservadora; especialmente útil con Sherlock).",
    ),
) -> None:
    """Ejecuta búsqueda combinada: username y/o email, en una sola corrida."""

    normalized_email = _normalize_email(email) if email else None
    categories = {c.strip().lower() for c in (category or []) if c.strip()} or None
    no_nsfw: bool | None
    if nsfw == NsfwPolicy.inherit:
        no_nsfw = None
    elif nsfw == NsfwPolicy.exclude:
        no_nsfw = True
    else:
        no_nsfw = False

    output_format = _auto_output_format(output_format)
    asyncio.run(
        _hunt_async(
            username=(username.strip() if username else None),
            email=normalized_email,
            deep_analyze=deep_analyze,
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
        )
    )


@app.command()
def wizard() -> None:
    """Wizard interactivo (menú) para ejecutar una búsqueda sin recordar flags."""

    console = _console
    print_banner(console)

    mode = Prompt.ask(
        "¿Qué quieres buscar?",
        choices=["username", "email", "ambos"],
        default="ambos",
    )

    username: str | None
    email: str | None

    if mode in ("username", "ambos"):
        u = Prompt.ask("Username", default="").strip()
        username = u or None
    else:
        username = None

    if mode in ("email", "ambos"):
        e = Prompt.ask("Email", default="").strip()
        email = _normalize_email(e) if e else None
    else:
        email = None

    if not username and not email:
        console.print("[red]Necesito al menos username o email.[/red]")
        raise typer.Exit(code=2)

    use_site_lists = Confirm.ask("¿Activar listas masivas (site-lists)?", default=False)
    use_sherlock = Confirm.ask("¿Activar Sherlock (400+ sitios)?", default=False)
    strict = Confirm.ask("¿Modo strict (reducir falsos positivos)?", default=False)
    username_sites_path: Path | None = None
    email_sites_path: Path | None = None
    sites_max_concurrency: int | None = None
    no_nsfw: bool | None = None
    category: set[str] | None = None

    if use_site_lists:
        settings = AppSettings()
        if username:
            default_u = ""
            if settings.username_sites_path:
                default_u = str(settings.username_sites_path)
            else:
                auto = get_default_list_path("wmn-data.json")
                if auto:
                    default_u = str(auto)
            p = Prompt.ask("Ruta JSON username-sites (wmn-data.json)", default=default_u).strip()
            username_sites_path = Path(p) if p else (Path(default_u) if default_u else None)
        if email:
            default_e = ""
            if settings.email_sites_path:
                default_e = str(settings.email_sites_path)
            else:
                auto = get_default_list_path("email-data.json")
                if auto:
                    default_e = str(auto)
            p = Prompt.ask("Ruta JSON email-sites (email-data.json)", default=default_e).strip()
            email_sites_path = Path(p) if p else (Path(default_e) if default_e else None)

        sites_max_concurrency = IntPrompt.ask(
            "Concurrencia para listas",
            default=int(settings.sites_max_concurrency),
        )
        no_nsfw = Confirm.ask("¿Excluir NSFW?", default=bool(settings.sites_no_nsfw))
        cats = Prompt.ask("Categorías (opcional, separadas por coma)", default="").strip()
        if cats:
            category = {c.strip().lower() for c in cats.split(",") if c.strip()} or None

    scan_localpart = False
    if email:
        scan_localpart = Confirm.ask("¿Probar también el localpart como username?", default=True)

    deep_analyze = Confirm.ask("¿Analizar con IA?", default=True)
    export_json = Confirm.ask("¿Exportar JSON a reports/?", default=False)
    export_pdf = Confirm.ask("¿Exportar PDF/HTML a reports/?", default=False)

    asyncio.run(
        _hunt_async(
            username=username,
            email=email,
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
        )
    )


@app.command()
def analyze(
    input_path: Path = typer.Argument(..., exists=True, dir_okay=False, help="Ruta a JSON exportado (reports/<target>.json)."),
    output_format: OutputFormat = typer.Option(
        OutputFormat.table,
        "--format",
        help="Formato de salida en terminal: table|json.",
    ),
    json_raw: bool = typer.Option(
        False,
        "--json-raw/--no-json-raw",
        help="(Solo --format json) Incluir `analysis.raw` (respuesta completa del proveedor IA).",
    ),
) -> None:
    """Ejecuta análisis IA sobre un JSON ya exportado.

    Útil cuando:
    - Escaneaste sin `--deep-analyze` y quieres analizar después.
    - Quieres re-ejecutar IA sin volver a consultar las fuentes.
    """

    raw = input_path.read_text(encoding="utf-8")
    person = PersonEntity.model_validate_json(raw)
    output_format = _auto_output_format(output_format)
    asyncio.run(
        _analyze_async(
            person=person,
            output_format=output_format,
            emit_json=True,
            include_raw_in_json=json_raw,
        )
    )


def run() -> None:
    """Wrapper de entrada para suprimir tracebacks por BrokenPipe.

    Caso típico: `osint-d2 scan ... --format json | head`.
    """

    try:
        app()
    except BrokenPipeError:
        # Evita "Exception ignored in..." y mantiene salida limpia.
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
