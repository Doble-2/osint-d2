"""Which sections an AI report may contain.

Personality, ideology and attack-surface sections are inferences about real
people, so they are opt-in (``OSINT_D2_SENSITIVE_INFERENCES`` or
``--sensitive-inferences``). Headings keep their numbers in every language.
"""

from __future__ import annotations

import re

from core.domain.language import Language

_SENSITIVE_SECTIONS = frozenset({"3", "5", "6"})

SCOPE_RESTRICTION: dict[Language, str] = {
    Language.ENGLISH: (
        "SCOPE (overrides anything above): act as a neutral analyst, not a profiler. Write only the sections "
        "headed '## 1.' (identity), '## 2.' (geo-temporal) and '## 4.' (technical/professional). Do NOT infer "
        "personality, psychology, political or ideological views, susceptibility to manipulation, or ways to attack "
        "the person, in the report or in the highlights."
    ),
    Language.SPANISH: (
        "ALCANCE (prevalece sobre todo lo anterior): actúa como analista neutral, no como perfilador. Escribe solo las "
        "secciones con encabezado '## 1.' (identidad), '## 2.' (geo-temporal) y '## 4.' (técnico/profesional). NO "
        "infieras personalidad, psicología, opiniones políticas o ideológicas, susceptibilidad a la manipulación ni "
        "formas de atacar a la persona, ni en el reporte ni en los puntos clave."
    ),
    Language.PORTUGUESE: (
        "ESCOPO (prevalece sobre tudo acima): atue como analista neutro, não como perfilador. Escreva apenas as seções "
        "com os títulos '## 1.' (identidade), '## 2.' (geotemporal) e '## 4.' (técnico/profissional). NÃO infira "
        "personalidade, psicologia, opiniões políticas ou ideológicas, suscetibilidade à manipulação nem formas de "
        "atacar a pessoa, nem no relatório nem nos destaques."
    ),
    Language.ARABIC: (
        "النطاق (يتقدم على كل ما سبق): تصرف كمحلل محايد لا كمحلل سلوك جنائي. اكتب فقط الأقسام ذات العناوين "
        "'## 1.' (الهوية) و'## 2.' (البعد الجغرافي الزمني) و'## 4.' (الجانب التقني والمهني). لا تستنتج الشخصية أو "
        "الحالة النفسية أو الآراء السياسية أو الأيديولوجية أو القابلية للتلاعب أو طرق مهاجمة الشخص، لا في التقرير ولا "
        "في النقاط البارزة."
    ),
    Language.RUSSIAN: (
        "ОБЪЁМ (важнее всего сказанного выше): действуй как нейтральный аналитик, а не как профайлер. Пиши только "
        "разделы с заголовками '## 1.' (личность), '## 2.' (география и время) и '## 4.' (технический и "
        "профессиональный профиль). НЕ делай выводов о личности, психологии, политических или идеологических взглядах, "
        "подверженности манипуляциям и способах атаковать человека ни в отчёте, ни в ключевых выводах."
    ),
}


def strip_sensitive_sections(summary: str) -> str:
    """Remove opt-in sections a model wrote anyway; the prompt alone guarantees nothing."""
    parts = re.split(r"(?m)^(?=##\s*\d+\.)", summary)
    kept = [
        part for part in parts
        if (match := re.match(r"##\s*(\d+)\.", part)) is None or match.group(1) not in _SENSITIVE_SECTIONS
    ]
    return "".join(kept).strip()
