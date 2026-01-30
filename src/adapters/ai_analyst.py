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
from core.domain.models import AnalysisReport, PersonEntity


def build_deepseek_client(*, api_key: str, base_url: str) -> AsyncOpenAI:
    return AsyncOpenAI(api_key=api_key, base_url=base_url)


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)

def _extract_json_object(text: str) -> str:
    t = text.strip()
    if not t:
        raise ValueError("Respuesta IA vacía")
    m = _JSON_FENCE_RE.search(t)
    #m= BeautifulSoup(t, "html.parser").find("code")
    if m:
        return m.group(1).strip()
    if t.startswith("{") and t.endswith("}"):
        return t
    start = t.find("{")
    end = t.rfind("}")
    if start != -1 and end != -1 and end > start:
        return t[start : end + 1].strip()
    raise ValueError("No se encontró un objeto JSON en la respuesta IA")


class _AIReportPayload(BaseModel):
    summary: str = Field(..., min_length=1)
    highlights: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


async def analyze_person(*, person: PersonEntity, settings: AppSettings | None = None) -> AnalysisReport:
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

    system_prompt = (
        "ACTÚA COMO: Un Perfilador Criminalista y Experto en Inteligencia de Amenazas (CTI).\n"
        "TU OBJETIVO: Construir un reporte psicológico y conductual del objetivo basado en su huella digital.\n"
        "TU MÉTODO: Deducción lógica agresiva (Chain of Thought). No solo describas, INFIERE.\n\n"

        "ANALIZA LAS SIGUIENTES 6 DIMENSIONES Y GENERA UN REPORTE EN FORMATO MARKDOWN:\n\n"

        "1. 🆔 IDENTIDAD Y DEMOGRAFÍA (Inferencia):\n"
        "   - ¿Nombre real probable?\n"
        "   - Rango de edad estimado (Basado en jerga, fecha creación de cuentas, referencias culturales).\n"
        "   - Género probable (Basado en patrones de lenguaje y pronombres).\n"
        "   - Nivel educativo estimado (Basado en gramática y complejidad técnica).\n\n"

        "2. 🌍 ANÁLISIS GEO-TEMPORAL (Crítico):\n"
        "   - Cruza timestamps de commits/posts/comentarios para triangular su ZONA HORARIA REAL.\n"
        "   - Infiere su RUTINA DE SUEÑO (¿Es un 'búho' que interactua de madrugada o una 'alondra'?)\n"
        "   - ¿Hay patrones de actividad que sugieran ubicación geográfica? (Ej. actividad laboral vs fines de semana)\n\n"

        "3. 🧠 PERFIL PSICOLÓGICO (Modelo OCEAN):\n"
        "   - Apertura: ¿Curioso, prueba cosas nuevas (o todo lo contrario)?\n"
        "   - Extraversión: ¿Interactúa mucho con otros o es más reservado?\n"
        "   - Responsabilidad: en caso de ser programdor, ¿Código limpio/comentarios o repositorios basura/abandonados?, en caso de que no  sea programador, ¿Es ordenado en sus posts y comentarios?\n"
        "   - Neuroticismo: ¿Se queja en los comentarios? ¿Tono agresivo o defensivo?\n"
        "   - Intereses Obsesivos: ¿De qué temas habla repetitivamente?\n\n"

        "4. 💻 PERFIL TÉCNICO Y PROFESIONAL: (en caso de tener indicios de ser desarrollador, ingeniero, o participar en la industria tech de alguan forma)\n"
        "   - Stack tecnológico real (no el que dice, sino el que usa).\n"
        "   - Nivel de Seniority real (Junior, Mid, Senior, Script Kiddie).\n"
        "   - ¿Desarrollador Corporativo, Freelance, Investigador o Hacker?\n\n"

        "5. ⚖️ IDEOLOGÍA Y VALORES:\n"
        "   - Infiere inclinación política o ética (izquierda - derecha, conservador - liberal, progresista, etc.) basándote en qué subreddits sigue o qué repositorios 'starrea', que posts sube a medium etc.\n\n"

        "6. ⚠️ VECTORES DE ATAQUE (OpSec):\n"
        "   - ¿Qué tan fácil sería hacerle Ingeniería Social? (¿Comparte demasiado?)\n"
        "   - ¿Ha expuesto correos personales o nombres de empresas?\n"
        "  - ¿Usa buenas prácticas de seguridad? (2FA, no reutiliza usernames, etc.)\n"
        "   - ¿Hay indicios de actividades maliciosas o hacking?\n\n"

        "FORMATO DE SALIDA (JSON ESTRICTO):\n"
        "{\n"
        "  'summary': 'Texto largo en Markdown con las 6 secciones detalladas arriba.',\n"
        "  'highlights': ['Lista de 3-5 deducciones rápidas y de alto impacto (Bullet points)'],\n"
        "  'confidence': 0.0 a 1.0 (Qué tan seguro estás de que los perfiles son la misma persona)\n"
        "}"
    )

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