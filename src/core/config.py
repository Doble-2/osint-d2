"""Configuración del Core.

Por qué aquí:
- Centraliza variables de entorno (pydantic-settings) sin contaminar la CLI.
- Permite que adaptadores (HTTP/IA) lean config de forma consistente.

Nota: se implementará en la siguiente iteración.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.domain.language import Language


class AppSettings(BaseSettings):
    """Configuración central de la aplicación.

    Por qué pydantic-settings:
    - Tipado + validación en el borde (env vars) sin ensuciar el Core con lógica.
    - Un único contrato de configuración para CLI/adapters.
    """

    model_config = SettingsConfigDict(
        env_prefix="OSINT_D2_",
        extra="ignore",
        case_sensitive=False,
        env_file=(".env",),
        env_file_encoding="utf-8",
    )

    http_timeout_seconds: float = Field(
        default=20.0,
        gt=0,
        description="Timeout por request (segundos).",
    )
    user_agent: str = Field(
        default="osint-d2/0.1 (+https://local)",
        min_length=1,
        description="User-Agent para peticiones OSINT.",
    )

    ai_api_key: str | None = Field(
        default=None,
        description="API key para el proveedor IA (DeepSeek compatible OpenAI).",
    )
    ai_base_url: str = Field(
        default="https://api.deepseek.com",
        min_length=8,
        description="Base URL compatible OpenAI (DeepSeek).",
    )
    ai_model: str = Field(
        default="deepseek-chat",
        min_length=1,
        description="Modelo por defecto para análisis.",
    )

    ai_timeout_seconds: float = Field(
        default=45.0,
        gt=0,
        description="Timeout para llamadas al proveedor IA (segundos).",
    )
    ai_max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Reintentos máximos ante fallos transitorios (rate limit, red).",
    )

    # Site-lists (data-driven, estilo WhatsMyName/email-data)
    sites_max_concurrency: int = Field(
        default=30,
        ge=1,
        le=500,
        description="Concurrencia máxima para el motor data-driven de listas de sitios.",
    )
    sites_no_nsfw: bool = Field(
        default=True,
        description="Excluir categorías NSFW en site-lists.",
    )
    username_sites_path: Path | None = Field(
        default=None,
        description="Ruta local a un JSON de sitios para username (p.ej. wmn-data.json).",
    )
    email_sites_path: Path | None = Field(
        default=None,
        description="Ruta local a un JSON de sitios para email (p.ej. email-data.json).",
    )

    default_language: Language = Field(
        default=Language.ENGLISH,
        description="Idioma por defecto para prompts y reportes (en/es).",
    )
