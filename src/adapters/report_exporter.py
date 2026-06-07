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

try:
    from weasyprint import HTML
except (ImportError, OSError):
    # Missing system libraries (cairo, pango, gdk-pixbuf) cause OSError.
    HTML = None

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
        if p.is_dir() and (p / "report.html").is_file():
            return p

    # Fallback final: intentar buscar relativa al CWD si estamos en modo dev
    cwd_templates = Path.cwd() / "src" / "templates"
    if cwd_templates.is_dir() and (cwd_templates / "report.html").is_file():
        return cwd_templates

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
        "ai_section_identity": "Identity",
        "ai_section_geotemporal": "Geo-Temporal",
        "ai_section_psychological": "OCEAN Profile",
        "ai_section_technical": "Technical / Professional",
        "ai_section_ideology": "Ideology",
        "ai_section_opsec": "OpSec / Attack Surface",
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
        "ai_section_identity": "Identidad",
        "ai_section_geotemporal": "Geo-Temporal",
        "ai_section_psychological": "Perfil OCEAN",
        "ai_section_technical": "Técnico / Profesional",
        "ai_section_ideology": "Ideología",
        "ai_section_opsec": "OpSec / Superficie de Ataque",
    },

    Language.PORTUGUESE: {
        "lang_code": "pt",
        "title_prefix": "OSINT-D2 • Dossiê",
        "watermark": "CONFIDENCIAL",
        "layout": {
            "top_left": "OSINT-D2",
            "top_right": "Gerado",
            "page_label": "Página",
        },
        "cover": {
            "badge": "DOSSIE CLASSIFICADO",
            "subtitle": "Relatório de Inteligência de Identidade",
            "target_label": "ALVO",
            "date_label": "DATA (UTC)",
            "report_label": "RELATÓRIO ID",
            "confidentiality_label": "CONFIDENCIALIDADE",
            "confidentiality_value": "INTERNA",
        },
        "toc_title": "00 // Índice",
        "toc_hint": "O índice inclui links internos e número de página.",
        "toc_entries": [
            {"anchor": "#sec-01", "label": "01 // Resumo de Inteligência"},
            {"anchor": "#sec-02", "label": "02 // Matriz de Pegada Confirmada"},
            {"anchor": "#sec-03", "label": "03 // Pistas para Revisão"},
            {"anchor": "#sec-04", "label": "04 // Evidências Textuais"},
            {"anchor": "#sec-05", "label": "05 // Metodologia"},
            {"anchor": "#sec-06", "label": "06 // Limitações"},
            {"anchor": "#sec-07", "label": "07 // Brechas (HIBP)"},
        ],
        "analysis_title": "01 // Resumo de Inteligência",
        "analysis_card_labels": {
            "total": "Total de perfis",
            "confirmed": "Confirmados",
            "unconfirmed": "Pendentes",
            "generated": "Gerado (UTC)",
        },
        "analysis_model_label": "Modelo",
        "analysis_confidence_label": "Confiança",
        "analysis_generated_label": "Gerado",
        "analysis_highlights_title": "Destaques",
        "analysis_absent": "A análise de IA não foi executada para este dossiê.",
        "analysis_footer_note": "Este dossiê resume evidências públicas. Atributos sensíveis estão excluídos.",
        "confirmed_title": "02 // Matriz de Pegada Confirmada",
        "confirmed_hint": "Perfis confirmados pela fonte.",
        "confirmed_headers": {
            "network": "Rede",
            "username": "Usuário",
            "source": "Fonte",
            "status": "Status",
            "url": "URL",
        },
        "status_confirmed": "CONFIRMADO",
        "unconfirmed_title": "03 // Pistas para Revisão",
        "unconfirmed_hint": "Perfis não confirmados para revisão manual.",
        "unconfirmed_none": "Não há perfis não confirmados neste escaneamento.",
        "unconfirmed_headers": {
            "network": "Rede",
            "username": "Usuário",
            "url": "URL",
        },
        "unconfirmed_source_label": "Fonte",
        "textual_title": "04 // Evidências Textuais",
        "textual_hint": "Amostras recentes quando a fonte as expõe.",
        "textual_none": "Não há evidências textuais adicionais neste escaneamento.",
        "textual_commits": "Commits recentes",
        "textual_comments": "Comentários recentes",
        "methodology_title": "05 // Metodologia",
        "methodology_hint": "Resumo do processo e critérios aplicados.",
        "methodology_points": [
            "Coleta multi-fonte: listas data-driven, verificações Sherlock e scrapers específicos.",
            "A confirmação prioriza evidências diretas como metadata HTTP, redirecionamentos e conteúdo verificado.",
            "A evidência textual inclui commits ou comentários recentes quando as fontes os expõem.",
            "O dossiê é renderizado a partir de HTML autocontido via WeasyPrint.",
        ],
        "limitations_title": "06 // Limitações",
        "limitations_points": [
            "Podem ocorrer falsos positivos/negativos se as fontes mudarem seu HTML ou bloquearem requests.",
            "Rate limiting ou requisitos de autenticação podem reduzir a cobertura.",
            "Trate a análise de IA como suporte à decisão; sempre valide com evidências primárias.",
        ],
        "breaches_title": "07 // Brechas (HIBP)",
        "breaches_hint": "Resultados do HaveIBeenPwned unifiedsearch para os emails detectados.",
        "breaches_none": "Nenhum breach-check foi executado para este dossiê.",
        "breaches_email_label": "Email",
        "breaches_status_label": "Status",
        "breaches_no_breaches": "Nenhuma brecha reportada para este email.",
        "breaches_request_failed": "A consulta de brechas falhou ou foi bloqueada.",
        "breaches_headers": {
            "title": "Brecha",
            "domain": "Domínio",
            "date": "Data",
            "records": "Registros",
            "classes": "Dados expostos",
        },
        "ai_section_identity": "Identidade",
        "ai_section_geotemporal": "Geo-Temporal",
        "ai_section_psychological": "Perfil OCEAN",
        "ai_section_technical": "Técnico / Profissional",
        "ai_section_ideology": "Ideologia",
        "ai_section_opsec": "OpSec / Superfície de Ataque",
    },
    Language.ARABIC: {
        "lang_code": "ar",
        "title_prefix": "OSINT-D2 • ملف",
        "watermark": "سري للغاية",
        "layout": {
            "top_left": "OSINT-D2",
            "top_right": "تم إنشاؤه",
            "page_label": "صفحة",
        },
        "cover": {
            "badge": "ملف سري",
            "subtitle": "تقرير استخبارات الهوية",
            "target_label": "الهدف",
            "date_label": "التاريخ (UTC)",
            "report_label": "معرف التقرير",
            "confidentiality_label": "السرية",
            "confidentiality_value": "داخلي",
        },
        "toc_title": "00 // المحتويات",
        "toc_hint": "تتضمن روابط التنقل أرقام الصفحات.",
        "toc_entries": [
            {"anchor": "#sec-01", "label": "01 // ملخص الاستخبارات"},
            {"anchor": "#sec-02", "label": "02 // مصفوفة البصمة المؤكدة"},
            {"anchor": "#sec-03", "label": "03 // الخيوط التي تتطلب المراجعة"},
            {"anchor": "#sec-04", "label": "04 // عينات الأدلة النصية"},
            {"anchor": "#sec-05", "label": "05 // المنهجية"},
            {"anchor": "#sec-06", "label": "06 // القيود"},
            {"anchor": "#sec-07", "label": "07 // انكشاف البيانات (HIBP)"},
        ],
        "analysis_title": "01 // ملخص الاستخبارات",
        "analysis_card_labels": {
            "total": "إجمالي الملفات الشخصية",
            "confirmed": "مؤكد",
            "unconfirmed": "قيد المراجعة",
            "generated": "تم إنشاؤه (UTC)",
        },
        "analysis_model_label": "النموذج",
        "analysis_confidence_label": "الثقة",
        "analysis_generated_label": "تم إنشاؤه",
        "analysis_highlights_title": "أبرز النقاط",
        "analysis_absent": "لم يتم تنفيذ تحليل الذكاء الاصطناعي لهذا الملف.",
        "analysis_footer_note": "يلخص هذا الملف الأدلة المتاحة للجمهور. تم استبعاد السمات الحساسة.",
        "confirmed_title": "02 // مصفوفة البصمة المؤكدة",
        "confirmed_hint": "ملفات شخصية تم تأكيدها بواسطة المصدر.",
        "confirmed_headers": {
            "network": "الشبكة",
            "username": "المعرف",
            "source": "المصدر",
            "status": "الحالة",
            "url": "الرابط",
        },
        "status_confirmed": "مؤكد",
        "unconfirmed_title": "03 // الخيوط التي تتطلب المراجعة",
        "unconfirmed_hint": "ملفات شخصية غير مؤكدة تم جمعها للمراجعة اليدوية.",
        "unconfirmed_none": "لم يتم اكتشاف أي ملفات شخصية غير مؤكدة في هذا المسح.",
        "unconfirmed_headers": {
            "network": "الشبكة",
            "username": "المعرف",
            "url": "الرابط",
        },
        "unconfirmed_source_label": "المصدر",
        "textual_title": "04 // عينات الأدلة النصية",
        "textual_hint": "عينات حديثة مقدمة من المصدر عند توفرها.",
        "textual_none": "لا توجد أدلة نصية إضافية متاحة لهذا المسح.",
        "textual_commits": "الالتزامات الحديثة",
        "textual_comments": "التعليقات الحديثة",
        "methodology_title": "05 // المنهجية",
        "methodology_hint": "ملخص العملية والمعايير.",
        "methodology_points": [
            "جمع متعدد المصادر: قوائم المواقع المستندة إلى البيانات، والتحقق عبر Sherlock، والكاشطات المخصصة.",
            "يعطي التأكيد الأولوية للأدلة المباشرة مثل بيانات HTTP الوصفية، وعمليات إعادة التوجيه، والمحتوى الذي تم التحقق منه.",
            "تتضمن الأدلة النصية الالتزامات أو التعليقات الحديثة عندما تكشف المصادر عنها.",
            "يتم عرض الملف من قالب HTML مستقل عبر WeasyPrint.",
        ],
        "limitations_title": "06 // القيود",
        "limitations_points": [
            "قد تحدث إيجابيات/سلبيات خاطئة عندما تغير المصادر HTML الخاص بها أو تحظر الطلبات.",
            "يمكن أن يقلل تحديد المعدل أو متطلبات المصادقة من التغطية.",
            "عامل تحليل الذكاء الاصطناعي كدعم للقرار؛ تحقق دائماً باستخدام الأدلة الأولية.",
        ],
        "breaches_title": "07 // انكشاف البيانات (HIBP)",
        "breaches_hint": "نتائج البحث الموحد في HaveIBeenPwned لرسائل البريد الإلكتروني المكتشفة.",
        "breaches_none": "لم يتم تنفيذ فحص الخروقات لهذا الملف.",
        "breaches_email_label": "البريد الإلكتروني",
        "breaches_status_label": "الحالة",
        "breaches_no_breaches": "لم يتم الإبلاغ عن أي خروقات لهذا البريد الإلكتروني.",
        "breaches_request_failed": "فشل طلب الخرق أو تم حظره.",
        "breaches_headers": {
            "title": "خرق",
            "domain": "المجال",
            "date": "التاريخ",
            "records": "السجلات",
            "classes": "فئات البيانات",
        },
        "ai_section_identity": "الهوية",
        "ai_section_geotemporal": "الجغرافي-الزمني",
        "ai_section_psychological": "ملف OCEAN",
        "ai_section_technical": "تقني / مهني",
        "ai_section_ideology": "الأيديولوجيا",
        "ai_section_opsec": "أمن العمليات / سطح الهجوم",
    },
    Language.RUSSIAN: {
        "lang_code": "ru",
        "title_prefix": "OSINT-D2 • Досье",
        "watermark": "КОНФИДЕНЦИАЛЬНО",
        "layout": {
            "top_left": "OSINT-D2",
            "top_right": "Создано",
            "page_label": "Страница",
        },
        "cover": {
            "badge": "СЕКРЕТНОЕ ДОСЬЕ",
            "subtitle": "Отчет по разведке личности",
            "target_label": "ЦЕЛЬ",
            "date_label": "ДАТА (UTC)",
            "report_label": "ID ОТЧЕТА",
            "confidentiality_label": "КОНФИДЕНЦИАЛЬНОСТЬ",
            "confidentiality_value": "ВНУТРЕННЕЕ",
        },
        "toc_title": "00 // Содержание",
        "toc_hint": "Ссылки навигации включают номера страниц.",
        "toc_entries": [
            {"anchor": "#sec-01", "label": "01 // Сводка разведданных"},
            {"anchor": "#sec-02", "label": "02 // Матрица подтвержденного следа"},
            {"anchor": "#sec-03", "label": "03 // Зацепки для проверки"},
            {"anchor": "#sec-04", "label": "04 // Образцы текстовых доказательств"},
            {"anchor": "#sec-05", "label": "05 // Методология"},
            {"anchor": "#sec-06", "label": "06 // Ограничения"},
            {"anchor": "#sec-07", "label": "07 // Утечки данных (HIBP)"},
        ],
        "analysis_title": "01 // Сводка разведданных",
        "analysis_card_labels": {
            "total": "Всего профилей",
            "confirmed": "Подтверждено",
            "unconfirmed": "На проверке",
            "generated": "Создано (UTC)",
        },
        "analysis_model_label": "Модель",
        "analysis_confidence_label": "Уверенность",
        "analysis_generated_label": "Создано",
        "analysis_highlights_title": "Ключевые моменты",
        "analysis_absent": "ИИ-анализ не выполнялся для этого досье.",
        "analysis_footer_note": "Это досье суммирует общедоступные доказательства. Чувствительные атрибуты исключены.",
        "confirmed_title": "02 // Матрица подтвержденного следа",
        "confirmed_hint": "Профили, подтвержденные источником.",
        "confirmed_headers": {
            "network": "Сеть",
            "username": "Имя пользователя",
            "source": "Источник",
            "status": "Статус",
            "url": "URL",
        },
        "status_confirmed": "ПОДТВЕРЖДЕНО",
        "unconfirmed_title": "03 // Зацепки для проверки",
        "unconfirmed_hint": "Неподтвержденные профили, собранные для ручной проверки.",
        "unconfirmed_none": "В этом сканировании не обнаружено неподтвержденных профилей.",
        "unconfirmed_headers": {
            "network": "Сеть",
            "username": "Имя пользователя",
            "url": "URL",
        },
        "unconfirmed_source_label": "Источник",
        "textual_title": "04 // Образцы текстовых доказательств",
        "textual_hint": "Недавние образцы, предоставленные источником, если доступны.",
        "textual_none": "Дополнительные текстовые доказательства отсутствуют для этого сканирования.",
        "textual_commits": "Недавние коммиты",
        "textual_comments": "Недавние комментарии",
        "methodology_title": "05 // Методология",
        "methodology_hint": "Сводка процесса и критериев.",
        "methodology_points": [
            "Сбор из нескольких источников: списки сайтов на основе данных, проверка через Sherlock и специализированные скреперы.",
            "Подтверждение отдает приоритет прямым доказательствам, таким как метаданные HTTP, перенаправления и проверенный контент.",
            "Текстовые доказательства включают недавние коммиты или комментарии, когда источники их раскрывают.",
            "Досье рендерится из автономного HTML-шаблона через WeasyPrint.",
        ],
        "limitations_title": "06 // Ограничения",
        "limitations_points": [
            "Возможны ложноположительные/отрицательные результаты, если источники меняют HTML или блокируют запросы.",
            "Ограничение скорости или требования аутентификации могут снизить охват.",
            "Рассматривайте ИИ-анализ как поддержку принятия решений; всегда проверяйте первичные доказательства.",
        ],
        "breaches_title": "07 // Утечки данных (HIBP)",
        "breaches_hint": "Результаты поиска HaveIBeenPwned unifiedsearch для обнаруженных email.",
        "breaches_none": "Проверка утечек не выполнялась для этого досье.",
        "breaches_email_label": "Email",
        "breaches_status_label": "Статус",
        "breaches_no_breaches": "Утечек для этого email не обнаружено.",
        "breaches_request_failed": "Запрос на проверку утечек не удался или был заблокирован.",
        "breaches_headers": {
            "title": "Утечка",
            "domain": "Домен",
            "date": "Дата",
            "records": "Записи",
            "classes": "Классы данных",
        },
        "ai_section_identity": "Идентичность",
        "ai_section_geotemporal": "Гео-Темпоральный",
        "ai_section_psychological": "Профиль OCEAN",
        "ai_section_technical": "Технический / Профессиональный",
        "ai_section_ideology": "Идеология",
        "ai_section_opsec": "OpSec / Поверхность атаки",
    },}


def _get_env() -> Environment:
    import markupsafe

    templates_dir = _resolve_templates_dir()
    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=select_autoescape(["html", "xml"]),
    )

    # ── Markdown → HTML filter ──
    try:
        import markdown as _md

        def _md_filter(text: str) -> markupsafe.Markup:
            """Convert markdown text to safe HTML."""
            if not text:
                return markupsafe.Markup("")
            html = _md.markdown(
                text,
                extensions=["tables", "fenced_code", "nl2br"],
            )
            return markupsafe.Markup(html)
    except ImportError:
        def _md_filter(text: str) -> markupsafe.Markup:  # type: ignore[misc]
            return markupsafe.Markup(f"<pre>{text}</pre>") if text else markupsafe.Markup("")

    env.filters["markdown"] = _md_filter
    return env


def _extract_identity_card(person: PersonEntity) -> dict[str, object]:
    """Extract enriched identity data from profile metadata for the PDF card."""
    card: dict[str, object] = {
        "avatar_url": None,
        "name": None,
        "bio": None,
        "location": None,
        "blog": None,
        "emails": [],
        "handles": [],
        "github_stats": None,
        "confirmed_networks": [],
        "created_at": None,
    }

    emails_set: set[str] = set()
    handles_set: set[str] = set()
    networks_set: set[str] = set()

    for p in person.profiles:
        if not p.exists:
            continue

        net = (p.network_name or "").lower()
        networks_set.add(net)

        u = (p.username or "").strip()
        if u:
            if "@" in u:
                emails_set.add(u.lower())
            else:
                handles_set.add(u)

        md = p.metadata if isinstance(p.metadata, dict) else {}

        # Priority: GitHub > GitLab > others for identity data.
        if net in ("github", "github_user") and md.get("name"):
            if not card["name"]:
                card["name"] = md.get("name")
            if not card["avatar_url"]:
                card["avatar_url"] = md.get("avatar") or md.get("avatar_url")
            if not card["bio"]:
                card["bio"] = md.get("bio")
            if not card["location"]:
                card["location"] = md.get("location")
            if not card["blog"]:
                card["blog"] = md.get("blog") or md.get("website")
            if not card["created_at"]:
                card["created_at"] = md.get("created_at")
            if md.get("public_repos") is not None or md.get("followers") is not None:
                card["github_stats"] = {
                    "repos": md.get("public_repos") or md.get("repos") or 0,
                    "followers": md.get("followers") or 0,
                    "following": md.get("following") or 0,
                }
        elif net == "gitlab" and not card["name"] and md.get("name"):
            card["name"] = md.get("name")
            if not card["avatar_url"]:
                card["avatar_url"] = md.get("avatar")
            if not card["bio"]:
                card["bio"] = md.get("bio")

        # Instagram: extract bio, name, and avatar from metadata.
        elif net == "instagram" and md:
            if not card["name"] and md.get("name"):
                card["name"] = md["name"]
            if not card["bio"] and (md.get("bio") or p.bio):
                card["bio"] = md.get("bio") or p.bio

    # ── Fallback avatar: try image_url from confirmed profiles ──
    # Priority order: instagram > telegram > twitter/x > any other.
    if not card["avatar_url"]:
        priority_order = ["instagram", "telegram", "x", "twitter"]
        avatar_candidates: list[tuple[int, str]] = []
        for p in person.profiles:
            if not p.exists or not p.image_url:
                continue
            net = (p.network_name or "").lower()
            try:
                rank = priority_order.index(net)
            except ValueError:
                rank = len(priority_order)
            avatar_candidates.append((rank, p.image_url))
        if avatar_candidates:
            avatar_candidates.sort(key=lambda x: x[0])
            card["avatar_url"] = avatar_candidates[0][1]

    card["emails"] = sorted(emails_set)
    card["handles"] = sorted(handles_set)
    card["confirmed_networks"] = sorted(networks_set)
    return card


def _parse_ai_sections(summary: str) -> dict[str, str]:
    """Parse AI summary into named sections based on ## N. headers."""
    import re

    sections: dict[str, str] = {}
    if not summary:
        return sections

    parts = re.split(r"(?=^## \d+\.)", summary, flags=re.MULTILINE)

    section_keys = {
        "1": "identity", "2": "geotemporal", "3": "psychological",
        "4": "technical", "5": "ideology", "6": "opsec",
    }

    for part in parts:
        part = part.strip()
        if not part:
            continue
        m = re.match(r"^## (\d+)\.", part)
        if m:
            num = m.group(1)
            key = section_keys.get(num, f"section_{num}")
            lines = part.split("\n", 1)
            sections[key] = lines[1].strip() if len(lines) > 1 else ""
        elif not sections:
            sections["intro"] = part

    return sections


_MAX_UNCONFIRMED = 20


def render_person_html(*, person: PersonEntity, language: Language) -> str:
    """Renderiza un HTML autocontenido para el reporte."""

    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    generated_at_local = datetime.now().astimezone().isoformat(timespec="seconds")

    profiles_total = len(person.profiles)
    profiles_confirmed = [p for p in person.profiles if p.exists]
    profiles_unconfirmed = [p for p in person.profiles if not p.exists]

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
            pass

    unconfirmed_by_source_map: dict[str, list] = {}
    for p in profiles_unconfirmed:
        source = _source_for_profile(p)
        unconfirmed_by_source_map.setdefault(source, []).append(p)

    unconfirmed_by_source = sorted(
        unconfirmed_by_source_map.items(),
        key=lambda kv: (kv[0] != "sherlock", kv[0]),
    )

    # Cap unconfirmed leads.
    total_unconfirmed = len(profiles_unconfirmed)
    capped_unconfirmed: list[tuple[str, list]] = []
    remaining = _MAX_UNCONFIRMED
    for source, items in unconfirmed_by_source:
        if remaining <= 0:
            break
        capped_unconfirmed.append((source, items[:remaining]))
        remaining -= min(len(items), remaining)

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
                "ok": bool(getattr(profile, "exists", False)),
            }
        )

    breach_entries.sort(key=lambda item: str(item.get("email") or ""))

    # ── Enriched data ──
    identity_card = _extract_identity_card(person)
    ai_sections: dict[str, str] = {}
    if person.analysis and person.analysis.summary:
        ai_sections = _parse_ai_sections(person.analysis.summary)
    confidence_pct = int(person.analysis.confidence * 100) if person.analysis else 0

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
        profiles_unconfirmed_count=total_unconfirmed,
        unconfirmed_by_source=capped_unconfirmed,
        unconfirmed_capped=total_unconfirmed > _MAX_UNCONFIRMED,
        unconfirmed_cap=_MAX_UNCONFIRMED,
        breach_entries=breach_entries,
        strings=strings,
        identity_card=identity_card,
        ai_sections=ai_sections,
        confidence_pct=confidence_pct,
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

    if HTML is None:
        raise ImportError(
            "WeasyPrint is not available (likely missing system libraries: "
            "cairo, pango, gdk-pixbuf). Install them and retry. "
            "PDF export is disabled."
        )

    import logging
    import warnings

    # Suppress noisy fontTools warnings ("fsSelection bit 5 (bold)…")
    # and WeasyPrint's own verbose logging.
    logging.getLogger("weasyprint").setLevel(logging.ERROR)
    logging.getLogger("fontTools").setLevel(logging.ERROR)
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*fsSelection.*")
        warnings.filterwarnings("ignore", message=".*instantiateVariableFont.*")
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        HTML(string=html, base_url=base_url).write_pdf(str(output_path))
    return output_path
