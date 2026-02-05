"""Adaptador para análisis IA (DeepSeek via OpenAI SDK).

Responsabilidad:
- Construir un payload de evidencia a partir de un `PersonEntity`.
- Llamar al proveedor IA (SDK OpenAI compatible) y parsear salida en JSON.
- Normalizar el resultado como `AnalysisReport`.
"""

from __future__ import annotations

import asyncio
import json
import random
import re
from typing import Any
#from bs4 import BeautifulSoup migrar a beatifulsoup 

from pydantic import BaseModel, Field
from openai import AsyncOpenAI

APIConnectionError: type[Exception]
APITimeoutError: type[Exception]
APIStatusError: type[Exception]
RateLimitError: type[Exception]

try:
    from openai import (  # type: ignore
        APIConnectionError as _APIConnectionError,
        APITimeoutError as _APITimeoutError,
        APIStatusError as _APIStatusError,
        RateLimitError as _RateLimitError,
    )

    APIConnectionError = _APIConnectionError
    APITimeoutError = _APITimeoutError
    APIStatusError = _APIStatusError
    RateLimitError = _RateLimitError
except Exception:  # pragma: no cover
    class _FallbackOpenAIError(Exception):
        pass

    APIConnectionError = _FallbackOpenAIError
    APITimeoutError = _FallbackOpenAIError
    APIStatusError = _FallbackOpenAIError
    RateLimitError = _FallbackOpenAIError

from core.config import AppSettings
from core.domain.language import Language
from core.domain.models import AnalysisReport, PersonEntity


def build_deepseek_client(*, api_key: str, base_url: str) -> AsyncOpenAI:
    return AsyncOpenAI(api_key=api_key, base_url=base_url)


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)


def _truncate_str(value: object, max_chars: int) -> str | None:
    if not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None
    if len(s) <= max_chars:
        return s
    return s[: max_chars - 1].rstrip() + "…"


def _limit_list(value: object, max_items: int) -> list[object] | None:
    if not isinstance(value, list):
        return None
    if not value:
        return None
    return value[:max_items]


def _compact_text_samples(value: object, *, max_items: int, max_chars_each: int) -> list[str] | None:
    items = _limit_list(value, max_items)
    if not items:
        return None
    out: list[str] = []
    for it in items:
        s = _truncate_str(it, max_chars_each)
        if s:
            out.append(s)
    return out or None


def _summary_has_six_sections(*, summary: str, language: Language) -> bool:
    text = (summary or "").strip()
    if not text:
        return False

    # Exigimos al menos encabezados 1 y 6 para evitar falsos positivos.
    if language == Language.SPANISH:
        return bool(re.search(r"(?m)^##\s*1\.", text)) and bool(re.search(r"(?m)^##\s*6\.", text))
    return bool(re.search(r"(?m)^##\s*1\.", text)) and bool(re.search(r"(?m)^##\s*6\.", text))


def _extract_json_object(text: str) -> str:
    """Obtiene el primer objeto JSON presente en la respuesta del proveedor."""
    match = _JSON_FENCE_RE.search(text)
    if match:
        return match.group(1).strip()

    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped

    start = stripped.find("{")
    end = stripped.rfind("}")
    if 0 <= start < end:
        candidate = stripped[start : end + 1]
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            pass

    raise ValueError("Could not locate a valid JSON object in the AI provider response.")


def _sanitize_summary_markdown(text: str) -> str:
    """Recorta basura frecuente en 'summary'.

    Algunos modelos añaden secciones como '## Highlights' o '## Confidence' dentro
    del Markdown; esas secciones YA existen como campos JSON.
    """

    if not isinstance(text, str):
        return ""

    summary = text.strip()
    if not summary:
        return summary

    # Mantener hasta el final de la sección 6 (y cortar cualquier nuevo heading '##' posterior).
    m6 = re.search(r"(?m)^##\s*6\.", summary)
    if m6:
        tail = summary[m6.end() :]
        m_next = re.search(r"(?m)^##\s+", tail)
        if m_next:
            summary = summary[: m6.end() + m_next.start()].rstrip()

    # Si el modelo no siguió '## 6.' pero igualmente metió '## Highlights', cortar allí.
    m_junk = re.search(r"(?im)^##\s*(highlights|confidence)\b", summary)
    if m_junk:
        summary = summary[: m_junk.start()].rstrip()

    return summary


def _build_system_prompt(language: Language) -> str:
    # Importante: este prompt está diseñado para minimizar alucinaciones.
    # No pedimos ni mostramos "chain of thought"; pedimos conclusiones breves y basadas en evidencia.
    if language == Language.SPANISH:
        return (
           "ACTÚA COMO: Un Perfilador Criminalista y Experto en Inteligencia de Amenazas (CTI).\n"
            "TU OBJETIVO: Construir un reporte psicológico y conductual del objetivo basado en su huella digital.\n"
            "TU MÉTODO: Deducción lógica agresiva (Chain of Thought). No solo describas, INFIERE.\n\n"
            "ANALIZA LAS SIGUIENTES 6 DIMENSIONES Y GENERA UN REPORTE EN FORMATO MARKDOWN:\n\n"
            "1. 🆔 IDENTIDAD Y DEMOGRAFÍA (Inferencia):\n"
            "   - ¿Nombre real probable?\n"
            "   - Rango de edad estimado (jerga, antigüedad de cuentas, referencias culturales).\n"
            "   - Género probable (patrones lingüísticos y pronombres).\n"
            "   - Nivel educativo estimado (gramática, complejidad técnica).\n\n"
            "2. 🌍 ANÁLISIS GEO-TEMPORAL (Crítico):\n"
            "   - Cruza timestamps de commits/posts/comentarios para triangular ZONA HORARIA REAL.\n"
            "   - Infiere rutina de sueño (búho nocturno vs alondra madrugadora).\n"
            "   - ¿Patrones que sugieran ubicación geográfica (actividad laboral vs fines de semana)?\n\n"
            "3. 🧠 PERFIL PSICOLÓGICO (Modelo OCEAN):\n"
            "   - Apertura: curiosidad y experimentación.\n"
            "   - Extraversión: nivel de interacción social.\n"
            "   - Responsabilidad: consistencia y orden en el trabajo/código.\n"
            "   - Neuroticismo: frustración, quejas, tono defensivo.\n"
            "   - Intereses obsesivos: temas o comunidades recurrentes.\n\n"
            "4. 💻 PERFIL TÉCNICO Y PROFESIONAL:\n"
            "   - Stack real (basado en actividad, no en lo que declara).\n"
            "   - Nivel de seniority (Junior, Mid, Senior, Script Kiddie).\n"
            "   - Arquetipo profesional (corporativo, freelance, investigador, hacker, creador, etc.).\n\n"
            "5. ⚖️ IDEOLOGÍA Y VALORES:\n"
            "   - Infiere inclinación política o ética a partir de comunidades, repositorios, publicaciones o likes.\n\n"
            "6. ⚠️ VECTORES DE ATAQUE (OpSec):\n"
            "   - Susceptibilidad a ingeniería social.\n"
            "   - Exposición de emails personales, empleadores o identidades reales.\n"
            "   - Higiene de seguridad (2FA, reutilización de alias, credenciales expuestas).\n"
            "   - Indicios de actividad maliciosa o hacking.\n\n"
            "IDIOMA DE RESPUESTA: Español neutro.\n"
            "FORMATO DE SALIDA (JSON ESTRICTO):\n"
            "{\n"
            "  \"summary\": \"Texto en Markdown con las seis secciones.\",\n"
            "  \"highlights\": [\"Lista de 3-5 deducciones rápidas.\"],\n"
            "  \"confidence\": 0.0 a 1.0\n"
            "}"
        )

    return (
          "ROLE: Criminal Profiler and Threat Intelligence Analyst.\n"
        "OBJECTIVE: Build a psychological and behavioural report using public evidence.\n"
        "METHOD: Aggressive logical deduction (Chain of Thought). Do not merely describe — infer.\n\n"
        "ANALYSE THE FOLLOWING SIX DIMENSIONS AND PRODUCE A MARKDOWN REPORT:\n\n"
        "1. 🆔 IDENTITY & DEMOGRAPHICS (Inference):\n"
        "   - Probable real name.\n"
        "   - Estimated age range (slang, account age, cultural references).\n"
        "   - Probable gender (linguistic cues, pronouns).\n"
        "   - Education level inferred from grammar, technical depth, writing quality.\n\n"
        "2. 🌍 GEO-TEMPORAL ANALYSIS (Critical):\n"
        "   - Cross activity timestamps to triangulate REAL TIMEZONE.\n"
        "   - Infer sleep routine (night owl vs early bird).\n"
        "   - Highlight patterns suggesting geography (workdays vs weekends).\n\n"
        "3. 🧠 PSYCHOLOGICAL PROFILE (OCEAN Model):\n"
        "   - Openness: curiosity and experimentation.\n"
        "   - Extraversion: level of social interaction.\n"
        "   - Conscientiousness: consistency and hygiene in output.\n"
        "   - Neuroticism: frustration, complaints, defensive tone.\n"
        "   - Obsessive interests: recurring themes or communities.\n\n"
        "4. 💻 TECHNICAL / PROFESSIONAL PROFILE:\n"
        "   - Real stack (evidence-based).\n"
        "   - Seniority estimate (Junior, Mid, Senior, Script Kiddie).\n"
        "   - Role archetype (corporate dev, freelancer, researcher, hacker, creator, etc.).\n\n"
        "5. ⚖️ IDEOLOGY & VALUES:\n"
        "   - Infer political or ethical leaning from communities, starred repos, publications or likes.\n\n"
        "6. ⚠️ ATTACK SURFACE (OpSec):\n"
        "   - Susceptibility to social engineering.\n"
        "   - Exposure of personal emails, employers, real identities.\n"
        "   - Security hygiene (2FA, alias reuse, credential leaks).\n"
        "   - Any hints of malicious or hacking activity.\n\n"
        "OUTPUT LANGUAGE: English only.\n"
        "OUTPUT FORMAT (STRICT JSON):\n"
        "{\n"
        "  \"summary\": \"Markdown text with the six sections above.\",\n"
        "  \"highlights\": [\"3-5 high-impact deductions.\"],\n"
        "  \"confidence\": 0.0 to 1.0\n"
        "}"
    )


def _build_system_prompt_compact(language: Language) -> str:
    """Versión compacta del prompt para modelos pequeños.

    Objetivo: reducir tokens (TPM) manteniendo el tono original y el mismo contrato de salida.
    """

    if language == Language.SPANISH:
        return (
            "ACTÚA COMO: Perfilador Criminalista y Analista CTI.\n"
            "OBJETIVO: Reporte psicológico y conductual desde huella digital.\n"
            "MÉTODO: Deducción lógica agresiva (Chain of Thought). INFIERE si hay evidencia; si no, dilo.\n\n"
            "ENTREGA: Markdown con estas 6 secciones EXACTAS (encabezados '## 1.' a '## 6.'): \n"
            "## 1. 🆔 Identidad y demografía (inferencia)\n"
            "## 2. 🌍 Análisis geo-temporal (zona horaria/rutina)\n"
            "## 3. 🧠 Perfil psicológico (OCEAN)\n"
            "## 4. 💻 Perfil técnico/profesional\n"
            "## 5. ⚖️ Ideología y valores\n"
            "## 6. ⚠️ Vectores de ataque (OpSec)\n\n"
            "FORMATO DE SALIDA: JSON ESTRICTO (sin texto extra):\n"
            "{\n"
            "  \"summary\": \"Markdown con las 6 secciones.\",\n"
            "  \"highlights\": [\"3-5 deducciones basadas en evidencia\"],\n"
            "  \"confidence\": 0.0 a 1.0\n"
            "}"
        )

    return (
        "ROLE: Criminal Profiler and CTI analyst.\n"
        "OBJECTIVE: Psychological/behavioural report from public footprint.\n"
        "METHOD: Aggressive logical deduction (Chain of Thought). Infer when grounded; otherwise say insufficient evidence.\n\n"
        "DELIVER: Markdown with these 6 EXACT sections (headings '## 1.' through '## 6.'): \n"
        "## 1. 🆔 Identity & demographics (inference)\n"
        "## 2. 🌍 Geo-temporal analysis (timezone/routine)\n"
        "## 3. 🧠 Psychological profile (OCEAN)\n"
        "## 4. 💻 Technical/professional profile\n"
        "## 5. ⚖️ Ideology & values\n"
        "## 6. ⚠️ Attack surface (OpSec)\n\n"
        "OUTPUT FORMAT: STRICT JSON only (no extra text):\n"
        "{\n"
        "  \"summary\": \"Markdown with the 6 sections.\",\n"
        "  \"highlights\": [\"3-5 evidence-grounded deductions\"],\n"
        "  \"confidence\": 0.0 to 1.0\n"
        "}"
    )


def _should_use_compact_prompt(*, base_url: str, model: str) -> bool:
    base = (base_url or "").lower()
    m = (model or "").lower()
    if "api.groq.com" not in base:
        return False
    return "8b" in m or "instant" in m


def _max_tokens_for_model(model: str) -> int:
    m = (model or "").lower()
    if "8b" in m or "instant" in m:
        return 1100
    return 1800


def _extract_hibp_breaches(meta: dict[str, Any]) -> dict[str, Any] | None:
    breaches_dump = meta.get("breaches")
    if not isinstance(breaches_dump, dict):
        return None
    breaches_list = breaches_dump.get("breaches")
    if not isinstance(breaches_list, list):
        return None
    breaches: list[dict[str, Any]] = []
    for item in breaches_list:
        if not isinstance(item, dict):
            continue
        breaches.append(
            {
                "title": item.get("title") or item.get("Title"),
                "domain": item.get("domain") or item.get("Domain"),
                "breach_date": item.get("breach_date") or item.get("BreachDate"),
                "pwn_count": item.get("pwn_count") or item.get("PwnCount"),
                "data_classes": item.get("data_classes") or item.get("DataClasses"),
            }
        )
    return {"count": len(breaches), "top": breaches[:10]}


def _safe_retry_after_seconds(exc: Exception) -> float | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    value = headers.get("retry-after") or headers.get("Retry-After")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except Exception:
        return None


def _looks_like_model_rejection(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(token in msg for token in ("model", "not found", "does not exist", "unsupported"))


class _AIReportPayload(BaseModel):
    summary: str = Field(..., min_length=1)
    highlights: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


def _is_local_base_url(url: str) -> bool:
    url_l = (url or "").strip().lower()
    return url_l.startswith("http://localhost") or url_l.startswith("http://127.0.0.1") or url_l.startswith(
        "http://0.0.0.0"
    )


def _heuristic_analysis(*, person: PersonEntity, language: Language, reason: str) -> AnalysisReport:
    profiles = list(person.profiles)
    confirmed = [p for p in profiles if getattr(p, "existe", False)]
    networks = sorted({(p.network_name or "").lower() for p in confirmed if p.network_name})
    emails = sorted({p.username for p in profiles if isinstance(getattr(p, "username", None), str) and "@" in p.username})

    breach_lines: list[str] = []
    for p in profiles:
        if (p.network_name or "").lower() != "hibp":
            continue
        md = p.metadata if isinstance(p.metadata, dict) else {}
        status = md.get("status_code")
        breaches_dump = md.get("breaches")
        breaches_list: list[dict[str, object]] = []
        if isinstance(breaches_dump, dict):
            maybe = breaches_dump.get("breaches")
            if isinstance(maybe, list):
                breaches_list = [b for b in maybe if isinstance(b, dict)]

        if status != 200:
            err = md.get("error")
            breach_lines.append(f"- {p.username}: status={status} error={err}")
            continue

        if not breaches_list:
            breach_lines.append(f"- {p.username}: 0 breaches")
            continue

        titles = ", ".join(str(b.get("title") or "") for b in breaches_list[:6] if b.get("title"))
        more = "" if len(breaches_list) <= 6 else f" (+{len(breaches_list) - 6} more)"
        breach_lines.append(f"- {p.username}: {len(breaches_list)} breaches → {titles}{more}")

    if language == Language.SPANISH:
        summary = [
            "## 1. 🆔 Identidad y demografía (inferencias)",
            "Evidencia insuficiente para inferir atributos personales de forma responsable.",
            "\n## 2. 🌍 Análisis geo-temporal",
            "No hay timestamps suficientes para triangular zona horaria.",
            "\n## 3. 🧠 Perfil psicológico (OCEAN)",
            "No se observa contenido textual confiable para un perfil psicológico.",
            "\n## 4. 💻 Perfil técnico/profesional",
            f"Perfiles confirmados: {len(confirmed)} / {len(profiles)}.",
            f"Redes confirmadas: {', '.join(networks) if networks else 'N/A'}.",
            "\n## 5. ⚖️ Ideología y valores",
            "Sin evidencia suficiente para inferencias ideológicas.",
            "\n## 6. ⚠️ OpSec / superficie de ataque",
            f"Emails observados: {', '.join(emails) if emails else 'N/A'}.",
        ]
        if breach_lines:
            summary.append("\nResultados de brechas (HIBP):\n" + "\n".join(breach_lines))
        summary.append(f"\n> Nota: análisis heurístico (sin IA remota). Motivo: {reason}.")
        highlights = [
            f"Perfiles confirmados: {len(confirmed)}.",
            f"Redes confirmadas: {', '.join(networks) if networks else 'N/A'}.",
        ]
        if breach_lines:
            highlights.append("Se detectaron resultados de HIBP (breach-check).")
        return AnalysisReport(
            summary="\n".join(summary).strip(),
            highlights=highlights,
            confidence=0.25,
            model="heuristic",
            raw={"reason": reason},
        )

    summary = [
        "## 1. 🆔 Identity & demographics (inference)",
        "Insufficient evidence to infer personal attributes responsibly.",
        "\n## 2. 🌍 Geo-temporal analysis",
        "Not enough timestamps to triangulate timezone.",
        "\n## 3. 🧠 Psychological profile (OCEAN)",
        "No reliable textual evidence for a psychological profile.",
        "\n## 4. 💻 Technical/professional profile",
        f"Confirmed profiles: {len(confirmed)} / {len(profiles)}.",
        f"Confirmed networks: {', '.join(networks) if networks else 'N/A'}.",
        "\n## 5. ⚖️ Ideology & values",
        "Insufficient evidence for ideological inferences.",
        "\n## 6. ⚠️ OpSec / attack surface",
        f"Observed emails: {', '.join(emails) if emails else 'N/A'}.",
    ]
    if breach_lines:
        summary.append("\nHIBP breach results:\n" + "\n".join(breach_lines))
    summary.append(f"\n> Note: heuristic analysis (no remote AI). Reason: {reason}.")
    highlights = [
        f"Confirmed profiles: {len(confirmed)}.",
        f"Confirmed networks: {', '.join(networks) if networks else 'N/A'}.",
    ]
    if breach_lines:
        highlights.append("HIBP breach-check returned results.")
    return AnalysisReport(
        summary="\n".join(summary).strip(),
        highlights=highlights,
        confidence=0.25,
        model="heuristic",
        raw={"reason": reason},
    )


def _looks_like_template_response(*, parsed: _AIReportPayload) -> bool:
    summary = (parsed.summary or "").strip().lower()
    if summary in (
        "markdown text with the six sections above.",
        "texto en markdown con las seis secciones.",
    ):
        return True

    placeholders = {
        "3-5 high-impact deductions.",
        "lista de 3-5 deducciones rápidas.",
        "3-5 high impact deductions.",
    }
    hl = [str(x).strip().lower() for x in (parsed.highlights or []) if isinstance(x, str)]
    if not hl:
        return True
    if len(hl) == 1 and hl[0] in placeholders:
        return True
    if any(x in placeholders for x in hl):
        return True

    return False


async def analyze_person(
    *,
    person: PersonEntity,
    language: Language,
    settings: AppSettings | None = None,
) -> AnalysisReport:
    """Genera un reporte de análisis IA a partir de evidencias públicas."""

    settings = settings or AppSettings()
    
    clean_person = person.model_copy()
        
    while True:
        to_remove = [p for p in clean_person.profiles if not p.existe]
        if not to_remove:
            break
        for p in to_remove:
            if p.existe == False:   
                clean_person.profiles.remove(p)
            
            
    api_key = (settings.ai_api_key or "").strip()
    if not api_key:
        # Sin API key: si es un provider local OpenAI-compatible, usamos dummy.
        # En providers hosted (DeepSeek/Groq/etc.) caemos a heurístico.
        if _is_local_base_url(settings.ai_base_url):
            api_key = "local"
        else:
            return _heuristic_analysis(person=clean_person, language=language, reason="missing_ai_api_key")

    client = AsyncOpenAI(
        api_key=api_key,
        base_url=settings.ai_base_url,
        timeout=settings.ai_timeout_seconds,
        max_retries=0,
    )

    configured_model = settings.ai_model
    system_prompt = (
        _build_system_prompt_compact(language)
        if _should_use_compact_prompt(base_url=settings.ai_base_url, model=configured_model)
        else _build_system_prompt(language)
    )

    # Preparación de evidencia normalizada (best-effort).
    profiles_data: list[dict[str, Any]] = []
    for p in clean_person.profiles:
        meta = p.metadata if isinstance(p.metadata, dict) else {}
        
        # Normaliza URL (evita querystrings ruidosas).
        clean_url = str(p.url).split('?')[0]

        profile_dict: dict[str, Any] = {
            "network": p.network_name,
            "username": p.username,
            "url": clean_url,
            "bio": _truncate_str(p.bio or meta.get("bio"), 420),
            "location": _truncate_str(meta.get("location") or meta.get("location_claim"), 140),
            "signals": {
                "display_name": _truncate_str(meta.get("name") or meta.get("display_name"), 160),
                "company": _truncate_str(meta.get("company"), 160),
                "blog": _truncate_str(meta.get("blog") or meta.get("website"), 220),
                "created_at": _truncate_str(meta.get("created_at") or meta.get("created_utc"), 64),
                "followers": meta.get("followers"),
                "following": meta.get("following"),
                "public_repos": meta.get("public_repos") or meta.get("repos"),
                "languages": (
                    _limit_list(meta.get("languages") or meta.get("tech_stack"), 25)
                    or _truncate_str(meta.get("languages") or meta.get("tech_stack"), 220)
                ),
            },
            # Evidencia opcional (puede no existir según el scraper)
            "activity_timestamps": _limit_list(meta.get("commits") or meta.get("timestamps"), 60),
            "text_samples": _compact_text_samples(meta.get("comments") or meta.get("texts"), max_items=16, max_chars_each=320),
        }

        if (p.network_name or "").lower() == "hibp":
            hibp = _extract_hibp_breaches(meta)
            if hibp:
                profile_dict["hibp_breaches"] = hibp

        # Eliminar claves vacías
        profile_dict = {k: v for k, v in profile_dict.items() if v}
        profiles_data.append(profile_dict)

    # Cap para evitar prompts gigantes cuando un scraper trae demasiado contenido.
    if len(profiles_data) > 30:
        profiles_data = profiles_data[:30]

    confirmed_networks = sorted({(p.network_name or "").lower() for p in clean_person.profiles if p.network_name})
    confirmed_urls = [str(p.url).split("?")[0] for p in clean_person.profiles if getattr(p, "url", None)]

    handles: list[str] = []
    emails: list[str] = []
    for p in clean_person.profiles:
        u = (p.username or "").strip()
        if not u:
            continue
        if "@" in u:
            emails.append(u.lower())
        else:
            handles.append(u)

    handle_counts: dict[str, int] = {}
    for h in handles:
        key = h.lower()
        handle_counts[key] = handle_counts.get(key, 0) + 1
    reused_handles = sorted([h for h, c in handle_counts.items() if c >= 2])

    breach_summary: list[dict[str, Any]] = []
    for p in clean_person.profiles:
        if (p.network_name or "").lower() != "hibp":
            continue
        md = p.metadata if isinstance(p.metadata, dict) else {}
        hibp = _extract_hibp_breaches(md)
        if hibp:
            breach_summary.append({"email": p.username, "count": hibp.get("count"), "top": hibp.get("top")})
    has_text = any(bool(p.get("text_samples")) for p in profiles_data)
    has_timestamps = any(bool(p.get("activity_timestamps")) for p in profiles_data)

    user_payload = {
        "target_query": clean_person.target,
        "evidence_count": len(profiles_data),
        "confirmed_networks": confirmed_networks,
        "confirmed_urls": confirmed_urls[:60],
        "signals": {
            "has_text_samples": has_text,
            "has_activity_timestamps": has_timestamps,
            "emails": sorted(set(emails))[:20],
            "handles": sorted(set(handles))[:40],
            "reused_handles": reused_handles[:20],
            "breach_summary": breach_summary[:10],
        },
        "profiles": profiles_data,
        "output_language": language.value,
    }

    request_messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
    ]

    last_error: Exception | None = None
    fallback_model: str | None = None
    base_url_l = (settings.ai_base_url or "").lower()
    if "api.groq.com" in base_url_l:
        # Modelo ampliamente disponible en Groq (fallback seguro).
        fallback_model = "llama-3.1-8b-instant"
    # Reintentos: el proveedor puede devolver timeouts o JSON malformado.
    for attempt in range(max(1, settings.ai_max_retries + 1)):
        try:
            used_model = configured_model
            response = await client.chat.completions.create(
                model=used_model,
                messages=request_messages,  # type: ignore[arg-type]
                temperature=0.2,
                max_tokens=_max_tokens_for_model(used_model),
            )

            content = (response.choices[0].message.content or "").strip()
            json_text = _extract_json_object(content)
            data: Any = json.loads(json_text)
            parsed = _AIReportPayload.model_validate(data)

            missing_sections = not _summary_has_six_sections(summary=parsed.summary, language=language)
            if _looks_like_template_response(parsed=parsed) or missing_sections:
                last_error = ValueError("ai_returned_template")
                if attempt >= settings.ai_max_retries:
                    break
                request_messages.append({"role": "assistant", "content": content})
                if language == Language.SPANISH:
                    if missing_sections:
                        fix = (
                            "No seguiste el formato requerido. "
                            "Reescribe SOLO el JSON válido: 'summary' debe ser Markdown e incluir las 6 secciones con encabezados '## 1.' hasta '## 6.' "
                            "y 'highlights' debe ser una lista real basada en la evidencia recibida."
                        )
                    else:
                        fix = (
                            "Tu JSON es un template (valores de ejemplo). "
                            "Reescribe SOLO el JSON con contenido real: 'summary' debe incluir las 6 secciones completas y "
                            "'highlights' debe ser una lista real basada en la evidencia recibida."
                        )
                else:
                    if missing_sections:
                        fix = (
                            "You did not follow the required format. "
                            "Rewrite ONLY valid JSON: 'summary' must be Markdown and include all six sections with headings '## 1.' through '## 6.' "
                            "and 'highlights' must be a real list grounded in the provided evidence."
                        )
                    else:
                        fix = (
                            "Your JSON is a template (example values). "
                            "Rewrite ONLY the JSON with real content: 'summary' must include all 6 sections and "
                            "'highlights' must be a real list grounded in the provided evidence."
                        )
                request_messages.append({"role": "user", "content": fix})
                await asyncio.sleep(0.5)
                continue

            raw: dict[str, object] = {}
            try:
                raw = response.model_dump()  # type: ignore
            except Exception:
                raw = {"raw_text": content}

            return AnalysisReport(
                summary=_sanitize_summary_markdown(parsed.summary),
                highlights=parsed.highlights,
                confidence=(
                    min(parsed.confidence, 0.55)
                    if (not has_text and not has_timestamps and len(profiles_data) >= 3)
                    else (min(parsed.confidence, 0.35) if (not has_text and not has_timestamps) else parsed.confidence)
                ),
                model=used_model,
                raw=raw,
            )

        except APIStatusError as exc:
            # 400/404 por modelo no disponible (muy común en presets): intentar fallback una vez.
            last_error = exc
            status = getattr(exc, "status_code", None)
            if (
                fallback_model
                and configured_model != fallback_model
                and status in (400, 404)
                and _looks_like_model_rejection(exc)
            ):
                configured_model = fallback_model
                # Si cambiamos a un modelo pequeño, también compactamos el prompt.
                request_messages[0]["content"] = (
                    _build_system_prompt_compact(language)
                    if _should_use_compact_prompt(base_url=settings.ai_base_url, model=configured_model)
                    else _build_system_prompt(language)
                )
                # No cuenta como 'fallo final': reintenta inmediato con el fallback.
                continue

            if status == 429:
                if attempt >= settings.ai_max_retries:
                    break
                retry_after = _safe_retry_after_seconds(exc)
                base = retry_after if retry_after is not None else (1.25 * (2**attempt))
                await asyncio.sleep(base + random.uniform(0.0, 0.35))
                continue
            break

        except (RateLimitError, APITimeoutError, APIConnectionError) as exc:
            last_error = exc
            if attempt >= settings.ai_max_retries:
                break
            retry_after = _safe_retry_after_seconds(exc)
            base = retry_after if retry_after is not None else (1.25 * (2**attempt))
            await asyncio.sleep(base + random.uniform(0.0, 0.35))

        except (json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            if attempt >= settings.ai_max_retries:
                break
            # Auto-corrección: pedir al modelo que devuelva SOLO JSON válido.
            request_messages.append({"role": "assistant", "content": content})
            if language == Language.SPANISH:
                fix = "Tu respuesta no fue un JSON válido. Reescribe SOLO el JSON válido (sin texto extra ni fences)."
            else:
                fix = "Your response was not valid JSON. Rewrite ONLY valid JSON (no extra text, no fences)."
            request_messages.append({"role": "user", "content": fix})
            await asyncio.sleep(0.5)

        except Exception as exc:
            last_error = exc
            break

    return _heuristic_analysis(
        person=clean_person,
        language=language,
        reason=f"provider_failed:{type(last_error).__name__ if last_error else 'unknown'}",
    )