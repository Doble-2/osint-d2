"""Adaptador para análisis IA (DeepSeek via OpenAI SDK).

Responsabilidad:
- Construir un payload de evidencia a partir de un `PersonEntity`.
- Llamar al proveedor IA (SDK OpenAI compatible) y parsear salida en JSON.
- Normalizar el resultado como `AnalysisReport`.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any
#from bs4 import BeautifulSoup migrar a beatifulsoup 

from pydantic import BaseModel, Field
from openai import AsyncOpenAI

try:
    from openai import APIConnectionError, APITimeoutError, APIStatusError, RateLimitError
except Exception:  # pragma: no cover
    APIConnectionError = APITimeoutError = APIStatusError = RateLimitError = Exception  # type: ignore

from core.config import AppSettings
from core.domain.language import Language
from core.domain.models import AnalysisReport, PersonEntity


def build_deepseek_client(*, api_key: str, base_url: str) -> AsyncOpenAI:
    return AsyncOpenAI(api_key=api_key, base_url=base_url)


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)


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


def _build_system_prompt(language: Language) -> str:
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


class _AIReportPayload(BaseModel):
    summary: str = Field(..., min_length=1)
    highlights: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


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
            
            
    if not settings.ai_api_key:
        raise ValueError("Falta OSINT_D2_AI_API_KEY en .env")

    client = AsyncOpenAI(
        api_key=settings.ai_api_key,
        base_url=settings.ai_base_url,
        timeout=settings.ai_timeout_seconds,
        max_retries=0,
    )

    system_prompt = _build_system_prompt(language)

    # Preparación de evidencia normalizada (best-effort).
    profiles_data = []
    for p in clean_person.profiles:
        meta = p.metadata if isinstance(p.metadata, dict) else {}
        
        # Normaliza URL (evita querystrings ruidosas).
        clean_url = str(p.url).split('?')[0]

        profile_dict = {
            "network": p.network_name,
            "username": p.username,
            "url": clean_url,
            "bio": p.bio or meta.get("bio"),
            "location_claim": meta.get("location"),
            
            # Campos opcionales, según la fuente haya aportado evidencia.
            "activity_timestamps": meta.get("commits"), # Para análisis de sueño
            "text_samples": meta.get("comments"),       # Para análisis psicológico/político
            "tech_stack": meta.get("languages"),        # Para perfil técnico
            "communities": meta.get("subreddits"),      # Para perfil ideológico
            "account_age": meta.get("created_at") or meta.get("created_utc"), # Para edad estimada
            "email_leaks": meta.get("emails"),          # Para vectores de ataque
            #"password_leaks": meta.get("passwords"),    # Para vectores de ataque
            "extra_metadata": meta,                     # Cualquier otro dato relevante
        }
        # Eliminar claves vacías
        profile_dict = {k: v for k, v in profile_dict.items() if v}
        profiles_data.append(profile_dict)

    user_payload = {
        "target_query": clean_person.target,
        "evidence_count": len(profiles_data),
        "raw_evidence": profiles_data,
        "output_language": language.value,
    }

    request_messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
    ]

    last_error: Exception | None = None
    # Reintentos: el proveedor puede devolver timeouts o JSON malformado.
    for attempt in range(max(1, settings.ai_max_retries + 1)):
        try:
            response = await client.chat.completions.create(
                model=settings.ai_model,
                messages=request_messages,
                temperature=0.4,
                max_tokens=6000,
            )

            content = (response.choices[0].message.content or "").strip()
            json_text = _extract_json_object(content)
            data: Any = json.loads(json_text)
            parsed = _AIReportPayload.model_validate(data)

            raw: dict[str, object] = {}
            try:
                raw = response.model_dump()  # type: ignore
            except Exception:
                raw = {"raw_text": content}

            return AnalysisReport(
                summary=parsed.summary,
                highlights=parsed.highlights,
                confidence=parsed.confidence,
                model=settings.ai_model,
                raw=raw,
            )

        except (RateLimitError, APITimeoutError, APIConnectionError) as exc:
            last_error = exc
            if attempt >= settings.ai_max_retries:
                break
            await asyncio.sleep(1.0 * (2**attempt))

        except (json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            if attempt >= settings.ai_max_retries:
                break
            # Auto-corrección: pedir al modelo que devuelva SOLO JSON válido.
            request_messages.append({"role": "assistant", "content": content})
            request_messages.append({
                "role": "user", 
                "content": "Tu respuesta no fue un JSON válido. Por favor, reescribe SOLO el JSON, asegúrate de cerrar las llaves."
            })
            await asyncio.sleep(0.5)

        except Exception as exc:
            last_error = exc
            break

    raise RuntimeError(f"Fallo crítico en el Perfilador IA: {last_error}")