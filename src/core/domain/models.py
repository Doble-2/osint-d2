"""Modelos del dominio (Pydantic v2).

Por qué Pydantic en el dominio:
- Nos da validación estricta y documentación autocontenida (Field) sin acoplar
  el Core a librerías de I/O.
- Facilita la serialización/normalización de datos OSINT de múltiples fuentes.

Nota:
- Estos modelos describen *qué* es la información, no *cómo* se obtiene.
"""

from __future__ import annotations

from datetime import datetime
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
    existe: bool = Field(
        default=False,
        description="Indica si el perfil existe según la verificación de la fuente.",
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
    imagen_url: str | None = Field(
        default=None,
        description="URL de avatar/imagen pública si está disponible.",
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
        default_factory=datetime.utcnow,
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


"""

{'Breaches': [{'Name': 'Twitter200M', 'Title': 'Twitter (200M)', 'Domain': 'twitter.com', 'BreachDate': '2021-01-01', 'AddedDate': '2023-01-05T20:49:16Z', 'ModifiedDate': '2023-01-05T20:49:16Z', 'PwnCount': 211524284, 'Description': 'In early 2023, <a href="https://www.bleepingcomputer.com/news/security/200-million-twitter-users-email-addresses-allegedly-leaked-online/" target="_blank" rel="noopener">over 200M records scraped from Twitter appeared on a popular hacking forum</a>. The data was obtained sometime in 2021 by abusing an API that enabled email addresses to be resolved to Twitter profiles. The subsequent results were then composed into a corpus of data containing email addresses alongside public Twitter profile information including names, usernames and follower counts.', 'LogoPath': 'https://logos.haveibeenpwned.com/Twitter.png', 'Attribution': None, 'DisclosureUrl': None, 'DataClasses': ['Email addresses', 'Names', 'Social media profiles', 'Usernames'], 'IsVerified': True, 'IsFabricated': False, 'IsSensitive': False, 'IsRetired': False, 'IsSpamList': False, 'IsMalware': False, 'IsSubscriptionFree': False, 'IsStealerLog': False}, {'Name': 'HeatGames', 'Title': 'HeatGames', 'Domain': 'heatgames.me', 'BreachDate': '2021-06-12', 'AddedDate': '2025-01-28T07:40:43Z', 'ModifiedDate': '2025-01-28T07:40:43Z', 'PwnCount': 647896, 'Description': 'In June 2021, the (now defunct) gaming website HeatGames suffered a data breach <a href="https://cybernews.com/security/billions-passwords-credentials-leaked-mother-of-all-breaches/" target="_blank" rel="noopener">that was later redistributed as part of a larger corpus of data</a>. The breach exposed almost 650k unique email addresses along with IP addresses, country and salted MD5 password hashes.', 'LogoPath': 'https://logos.haveibeenpwned.com/HeatGames.png', 'Attribution': None, 'DisclosureUrl': None, 'DataClasses': ['Email addresses', 'Geographic locations', 'IP addresses', 'Passwords'], 'IsVerified': True, 'IsFabricated': False, 'IsSensitive': False, 'IsRetired': False, 'IsSpamList': False, 'IsMalware': False, 'IsSubscriptionFree': False, 'IsStealerLog': False}], 'Pastes': None}
"""
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