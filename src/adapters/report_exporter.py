"""Exportación de reportes.

Por qué está en adapters:
- PDF/HTML son detalles de infraestructura (WeasyPrint/Jinja2).
- El Core solo conoce el agregado `PersonEntity` y el `AnalysisReport`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

from core.domain.language import Language
from core.domain.models import PersonEntity


_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_TEMPLATES_DIR_FALLBACK = Path(__file__).resolve().parents[1] / "templates"


def _resolve_templates_dir() -> Path:
    candidates: list[Path] = []

    if _TEMPLATES_DIR.is_dir():
        candidates.append(_TEMPLATES_DIR)
    if _TEMPLATES_DIR_FALLBACK.is_dir():
        candidates.append(_TEMPLATES_DIR_FALLBACK)

    # PyInstaller: los archivos se extraen bajo sys._MEIPASS.
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        base = Path(str(meipass))
        # Mapeos previstos en el spec: adapters/templates y templates
        candidates.extend(
            [
                base / "adapters" / "templates",
                base / "templates",
            ]
        )

    for p in candidates:
        if p.is_dir():
            return p

    return _TEMPLATES_DIR

_STRINGS: dict[Language, dict[str, object]] = {
    Language.ENGLISH: {
        "lang_code": "en",
        "title_prefix": "OSINT-D2 • Dossier",
        "watermark": "CLASSIFIED",
        "layout": {
            "top_left": "OSINT-D2",
            "top_right": "Generated",
            "page_label": "Page",
        },
        "cover": {
            "badge": "CLASSIFIED DOSSIER",
            "subtitle": "Identity Intelligence Brief",
            "target_label": "SUBJECT",
            "date_label": "DATE (UTC)",
            "report_label": "REPORT ID",
            "confidentiality_label": "CONFIDENTIALITY",
            "confidentiality_value": "INTERNAL",
        },
        "toc_title": "00 // Contents",
        "toc_hint": "Navigation links include page numbers.",
        "toc_entries": [
            {"anchor": "#sec-01", "label": "01 // Intelligence Summary"},
            {"anchor": "#sec-02", "label": "02 // Confirmed Footprint Matrix"},
            {"anchor": "#sec-03", "label": "03 // Leads Requiring Review"},
            {"anchor": "#sec-04", "label": "04 // Textual Evidence Samples"},
            {"anchor": "#sec-05", "label": "05 // Methodology"},
            {"anchor": "#sec-06", "label": "06 // Limitations"},
            {"anchor": "#sec-07", "label": "07 // Breach Exposure (HIBP)"},
        ],
        "analysis_title": "01 // Intelligence Summary",
        "analysis_card_labels": {
            "total": "Total profiles",
            "confirmed": "Confirmed",
            "unconfirmed": "Pending review",
            "generated": "Generated (UTC)",
        },
        "analysis_model_label": "Model",
        "analysis_confidence_label": "Confidence",
        "analysis_generated_label": "Generated",
        "analysis_highlights_title": "Highlights",
        "analysis_absent": "AI analysis was not executed for this dossier.",
        "analysis_footer_note": "This dossier summarizes publicly available evidence. Sensitive attributes are excluded.",
        "confirmed_title": "02 // Confirmed Footprint Matrix",
        "confirmed_hint": "Profiles confirmed by the source.",
        "confirmed_headers": {
            "network": "Network",
            "username": "Handle",
            "source": "Source",
            "status": "Status",
            "url": "URL",
        },
        "status_confirmed": "CONFIRMED",
        "unconfirmed_title": "03 // Leads Requiring Review",
        "unconfirmed_hint": "Unconfirmed profiles collected for manual review.",
        "unconfirmed_none": "No unconfirmed profiles were detected in this scan.",
        "unconfirmed_headers": {
            "network": "Network",
            "username": "Handle",
            "url": "URL",
        },
        "unconfirmed_source_label": "Source",
        "textual_title": "04 // Textual Evidence Samples",
        "textual_hint": "Recent samples provided by the source when available.",
        "textual_none": "No additional textual evidence is available for this scan.",
        "textual_commits": "Recent commits",
        "textual_comments": "Recent comments",
        "methodology_title": "05 // Methodology",
        "methodology_hint": "Process summary and criteria.",
        "methodology_points": [
            "Multi-source collection: data-driven site lists, Sherlock verification, and bespoke scrapers.",
            "Confirmation prioritizes direct evidence such as HTTP metadata, redirects, and verified content.",
            "Textual evidence includes recent commits or comments when sources expose them.",
            "Dossier export rendered from a self-contained HTML template via WeasyPrint.",
        ],
        "limitations_title": "06 // Limitations",
        "limitations_points": [
            "False positives/negatives may occur when sources change their HTML or block requests.",
            "Rate limiting or authentication requirements can reduce coverage.",
            "Treat AI analysis as decision support; always validate with primary evidence.",
        ],
        "breaches_title": "07 // Breach Exposure (HIBP)",
        "breaches_hint": "HaveIBeenPwned unifiedsearch results for discovered emails.",
        "breaches_none": "No breach checks were executed for this dossier.",
        "breaches_email_label": "Email",
        "breaches_status_label": "Status",
        "breaches_no_breaches": "No breaches reported for this email.",
        "breaches_request_failed": "Breach request failed or was blocked.",
        "breaches_headers": {
            "title": "Breach",
            "domain": "Domain",
            "date": "Date",
            "records": "Records",
            "classes": "Data classes",
        },
    },
    Language.SPANISH: {
        "lang_code": "es",
        "title_prefix": "OSINT-D2 • Reporte",
        "watermark": "CONFIDENCIAL",
        "layout": {
            "top_left": "OSINT-D2",
            "top_right": "Generado",
            "page_label": "Página",
        },
        "cover": {
            "badge": "EXPEDIENTE CLASIFICADO",
            "subtitle": "Informe de Inteligencia de Identidad",
            "target_label": "TARGET",
            "date_label": "FECHA (UTC)",
            "report_label": "REPORTE ID",
            "confidentiality_label": "CONFIDENCIALIDAD",
            "confidentiality_value": "INTERNA",
        },
        "toc_title": "00 // Índice",
        "toc_hint": "El índice incluye enlaces internos y número de página.",
        "toc_entries": [
            {"anchor": "#sec-01", "label": "01 // Resumen de Inteligencia"},
            {"anchor": "#sec-02", "label": "02 // Matriz de Huella Confirmada"},
            {"anchor": "#sec-03", "label": "03 // Pistas a Revisar"},
            {"anchor": "#sec-04", "label": "04 // Evidencia Textual"},
            {"anchor": "#sec-05", "label": "05 // Metodología"},
            {"anchor": "#sec-06", "label": "06 // Limitaciones"},
            {"anchor": "#sec-07", "label": "07 // Brechas (HIBP)"},
        ],
        "analysis_title": "01 // Resumen de Inteligencia",
        "analysis_card_labels": {
            "total": "Total perfiles",
            "confirmed": "Confirmados",
            "unconfirmed": "Pendientes",
            "generated": "Generado (UTC)",
        },
        "analysis_model_label": "Modelo",
        "analysis_confidence_label": "Confianza",
        "analysis_generated_label": "Generado",
        "analysis_highlights_title": "Puntos clave",
        "analysis_absent": "No se ejecutó análisis IA para este expediente.",
        "analysis_footer_note": "Este expediente resume evidencia pública. No incluye atributos sensibles.",
        "confirmed_title": "02 // Matriz de Huella Confirmada",
        "confirmed_hint": "Perfiles confirmados por la fuente.",
        "confirmed_headers": {
            "network": "Red",
            "username": "Usuario",
            "source": "Fuente",
            "status": "Estado",
            "url": "Enlace",
        },
        "status_confirmed": "CONFIRMADO",
        "unconfirmed_title": "03 // Pistas a Revisar",
        "unconfirmed_hint": "Perfiles no confirmados para revisión manual.",
        "unconfirmed_none": "No hay perfiles no confirmados en este escaneo.",
        "unconfirmed_headers": {
            "network": "Red",
            "username": "Usuario",
            "url": "URL",
        },
        "unconfirmed_source_label": "Fuente",
        "textual_title": "04 // Evidencia Textual",
        "textual_hint": "Muestras recientes cuando la fuente las expone.",
        "textual_none": "No hay evidencia textual adicional en este escaneo.",
        "textual_commits": "Commits recientes",
        "textual_comments": "Comentarios recientes",
        "methodology_title": "05 // Metodología",
        "methodology_hint": "Resumen del proceso y criterios aplicados.",
        "methodology_points": [
            "Recolección multi-fuente: listas data-driven, verificaciones Sherlock y scrapers específicos.",
            "La confirmación prioriza evidencia directa como metadata HTTP, redirecciones y contenido verificado.",
            "La evidencia textual incluye commits o comentarios recientes cuando las fuentes los exponen.",
            "El expediente se renderiza desde HTML autocontenido mediante WeasyPrint.",
        ],
        "limitations_title": "06 // Limitaciones",
        "limitations_points": [
            "Pueden existir falsos positivos/negativos si las fuentes cambian HTML o bloquean requests.",
            "El rate limiting o la autenticación pueden reducir la cobertura.",
            "Trata el análisis IA como apoyo; valida siempre con evidencia primaria.",
        ],
        "breaches_title": "07 // Brechas (HIBP)",
        "breaches_hint": "Resultados de HaveIBeenPwned unifiedsearch para los correos detectados.",
        "breaches_none": "No se ejecutó breach-check en este expediente.",
        "breaches_email_label": "Email",
        "breaches_status_label": "Estado",
        "breaches_no_breaches": "No se reportan brechas para este correo.",
        "breaches_request_failed": "La consulta de brechas falló o fue bloqueada.",
        "breaches_headers": {
            "title": "Brecha",
            "domain": "Dominio",
            "date": "Fecha",
            "records": "Registros",
            "classes": "Datos expuestos",
        },
    },
}


def _get_env() -> Environment:
    templates_dir = _resolve_templates_dir()
    return Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=select_autoescape(["html", "xml"]),
    )


def render_person_html(*, person: PersonEntity, language: Language) -> str:
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

    breach_entries: list[dict[str, object]] = []
    for profile in person.profiles:
        if getattr(profile, "network_name", None) != "hibp":
            continue
        md = getattr(profile, "metadata", None)
        if not isinstance(md, dict):
            continue

        breach_entries.append(
            {
                "email": str(getattr(profile, "username", "")) or str(md.get("email") or ""),
                "url": str(getattr(profile, "url", "")),
                "status_code": md.get("status_code"),
                "error": md.get("error"),
                "breach_count": md.get("breach_count"),
                "breaches": (md.get("breaches") or {}),
                "ok": bool(getattr(profile, "existe", False)),
            }
        )

    breach_entries.sort(key=lambda item: str(item.get("email") or ""))

    report_id = f"{person.target}:{generated_at}"
    template = _get_env().get_template("report.html")
    strings = _STRINGS.get(language, _STRINGS[Language.ENGLISH])
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
        breach_entries=breach_entries,
        strings=strings,
    )


def export_person_html(*, person: PersonEntity, output_path: Path, language: Language) -> Path:
    """Exporta el agregado como HTML.

    Por qué existe:
    - Sirve como fallback cuando el render PDF no está soportado por el entorno.
    - Útil para depurar el contenido del reporte y el template.
    """

    output_path.parent.mkdir(parents=True, exist_ok=True)
    html = render_person_html(person=person, language=language)
    output_path.write_text(html, encoding="utf-8")
    return output_path


def export_person_pdf(*, person: PersonEntity, output_path: Path, language: Language) -> Path:
    """Exporta el agregado `PersonEntity` como PDF.

    Diseño:
    - Sincrónico: WeasyPrint es CPU/IO local. La CLI puede ejecutarlo en un
      thread si fuese necesario más adelante.
    """

    output_path.parent.mkdir(parents=True, exist_ok=True)
    html = render_person_html(person=person, language=language)
    base_url = str(_resolve_templates_dir())
    HTML(string=html, base_url=base_url).write_pdf(str(output_path))
    return output_path
