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
    # On Windows, missing GTK libraries can cause OSError during import.
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
    },}


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

    if HTML is None:
        raise ImportError(
            "WeasyPrint is not available (likely missing GTK libraries on Windows). "
            "PDF export is disabled."
        )

    HTML(string=html, base_url=base_url).write_pdf(str(output_path))
    return output_path
