"""Exportación de reportes.

Por qué está en adapters:
- PDF/HTML son detalles de infraestructura (WeasyPrint/Jinja2).
- El Core solo conoce el agregado `PersonEntity` y el `AnalysisReport`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

from core.domain.models import PersonEntity


_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_TEMPLATES_DIR_FALLBACK = Path(__file__).resolve().parents[1] / "templates"


def _get_env() -> Environment:
    templates_dir = _TEMPLATES_DIR if _TEMPLATES_DIR.is_dir() else _TEMPLATES_DIR_FALLBACK
    return Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=select_autoescape(["html", "xml"]),
    )


def render_person_html(*, person: PersonEntity) -> str:
    """Renderiza un HTML autocontenido para el reporte."""

    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    generated_at_local = datetime.now().astimezone().isoformat(timespec="seconds")

    profiles_total = len(person.profiles)
    profiles_confirmed = [p for p in person.profiles if p.existe]
    profiles_unconfirmed = [p for p in person.profiles if not p.existe]

    def _source_for_profile(profile) -> str:
        md = getattr(profile, "metadata", None)
        if isinstance(md, dict):
            value = md.get("source")
            if value:
                return str(value)
        return "unknown"

    for p in person.profiles:
        try:
            setattr(p, "_source", _source_for_profile(p))
        except Exception:
            # Best-effort: si el modelo es inmutable, omitimos el campo.
            pass

    unconfirmed_by_source_map: dict[str, list] = {}
    for p in profiles_unconfirmed:
        source = _source_for_profile(p)
        unconfirmed_by_source_map.setdefault(source, []).append(p)

    unconfirmed_by_source = sorted(
        unconfirmed_by_source_map.items(),
        key=lambda kv: (kv[0] != "sherlock", kv[0]),
    )

    report_id = f"{person.target}:{generated_at}"
    template = _get_env().get_template("report.html")
    return template.render(
        person=person,
        generated_at=generated_at,
        generated_at_local=generated_at_local,
        report_id=report_id,
        profiles_total=profiles_total,
        profiles_confirmed=profiles_confirmed,
        profiles_confirmed_count=len(profiles_confirmed),
        profiles_unconfirmed_count=len(profiles_unconfirmed),
        unconfirmed_by_source=unconfirmed_by_source,
    )


def export_person_html(*, person: PersonEntity, output_path: Path) -> Path:
    """Exporta el agregado como HTML.

    Por qué existe:
    - Sirve como fallback cuando el render PDF no está soportado por el entorno.
    - Útil para depurar el contenido del reporte y el template.
    """

    output_path.parent.mkdir(parents=True, exist_ok=True)
    html = render_person_html(person=person)
    output_path.write_text(html, encoding="utf-8")
    return output_path


def export_person_pdf(*, person: PersonEntity, output_path: Path) -> Path:
    """Exporta el agregado `PersonEntity` como PDF.

    Diseño:
    - Sincrónico: WeasyPrint es CPU/IO local. La CLI puede ejecutarlo en un
      thread si fuese necesario más adelante.
    """

    output_path.parent.mkdir(parents=True, exist_ok=True)
    html = render_person_html(person=person)
    base_url = str(_TEMPLATES_DIR if _TEMPLATES_DIR.is_dir() else _TEMPLATES_DIR_FALLBACK)
    HTML(string=html, base_url=base_url).write_pdf(str(output_path))
    return output_path
