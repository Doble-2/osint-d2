"""Modelos del dominio (Pydantic v2).

Por qué Pydantic en el dominio:
- Nos da validación estricta y documentación autocontenida (Field) sin acoplar
  el Core a librerías de I/O.
- Facilita la serialización/normalización de datos OSINT de múltiples fuentes.

Nota:
- Estos modelos describen *qué* es la información, no *cómo* se obtiene.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field
from pydantic.config import ConfigDict


class SocialProfile(BaseModel):
    """Representa un perfil social encontrado (o verificado como inexistente).

    Por qué existe:
    - Unifica el resultado de múltiples scanners (GitHub, Sherlock-like, etc.)
      en una estructura común.
    - Permite adjuntar metadatos heterogéneos sin perder trazabilidad.
    """

    model_config = ConfigDict(populate_by_name=True)

    url: str = Field(
        ...,
        description="URL canónica del perfil en la red social.",
    )
    username: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Identificador/handle consultado o detectado.",
    )
    network_name: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Nombre de la red/plataforma (p.ej. 'github', 'x', 'linkedin').",
    )
    exists: bool = Field(
        default=False,
        description="Whether the profile was confirmed to exist by the source.",
        alias="existe",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Metadatos arbitrarios (headers, métricas, evidencias, etc.).",
    )
    bio: str | None = Field(
        default=None,
        max_length=10_000,
        description="Bio/descripcion pública si está disponible.",
    )
    image_url: str | None = Field(
        default=None,
        description="URL de avatar/imagen pública si está disponible.",
        alias="imagen_url",
    )


class AnalysisReport(BaseModel):
    """Reporte de análisis producido por la capa de IA.

    Por qué es un modelo separado:
    - La IA produce un artefacto con semántica distinta a los hallazgos brutos.
    - Permite evolucionar el esquema del reporte sin romper el agregado Persona.
    """

    summary: str = Field(
        ...,
        min_length=1,
        max_length=20_000,
        description="Resumen ejecutivo del análisis (correlación y contexto).",
    )
    highlights: list[str] = Field(
        default_factory=list,
        description="Puntos clave extraídos del conjunto de evidencias.",
    )
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Confianza normalizada (0..1) del análisis.",
    )
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Momento de generación del reporte (UTC).",
    )
    model: str | None = Field(
        default=None,
        description="Identificador del modelo IA utilizado (si aplica).",
    )
    raw: dict[str, Any] = Field(
        default_factory=dict,
        description="Carga útil cruda para auditoría/trazabilidad (opcional).",
    )


class PersonEntity(BaseModel):
    """Agregado principal: una identidad investigada.

    Por qué un agregado:
    - Centraliza el estado de la investigación (perfiles + análisis) para
      facilitar exportación, persistencia y presentación.
    """

    target: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="Target investigado (típicamente username o alias).",
    )
    profiles: list[SocialProfile] = Field(
        default_factory=list,
        description="Perfiles encontrados/checados en múltiples redes.",
    )
    analysis: AnalysisReport | None = Field(
        default=None,
        description="Reporte IA (presente solo si se ejecuta deep analysis).",
    )

class HaveibeenpwnedProfiles(BaseModel):
    model_config = ConfigDict(extra="ignore")

    email: str = Field(
        ...,
        description="Correo electrónico consultado en Have I Been Pwned.",
    )
    breaches: list[HaveibeenpwnedBreach] = Field(
        default_factory=list,
        description="Lista de brechas en las que se encontró el correo.",
    )

class HaveibeenpwnedBreach(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    title: str = Field(
        ...,
        alias="Title",
        description="Título de la brecha.",
    )
    domain: str = Field(
        ...,
        alias="Domain",
        description="Dominio asociado a la brecha.",
    )
    breach_date: str = Field(
        ...,
        alias="BreachDate",
        description="Fecha de la brecha.",
    )
    pwn_count: int = Field(
        ...,
        alias="PwnCount",
        description="Número de cuentas comprometidas en la brecha.",
    )
    description: str = Field(
        ...,
        alias="Description",
        description="Descripción de la brecha.",
    )
    data_classes: list[str] = Field(
        default_factory=list,
        alias="DataClasses",
        description="Tipos de datos comprometidos en la brecha.",
    )