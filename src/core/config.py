"""Configuración del Core.

Por qué aquí:
- Centraliza variables de entorno (pydantic-settings) sin contaminar la CLI.
- Permite que adaptadores (HTTP/IA) lean config de forma consistente.

Nota: se implementará en la siguiente iteración.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.domain.language import Language


def get_user_config_dir() -> Path:
    """Directorio de configuración por usuario (cross-platform, sin dependencias).

    Objetivo: permitir un instalador/PyInstaller sin necesidad de editar `.env` en el proyecto.
    """

    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", str(Path.home())))
        return base / "osint-d2"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "osint-d2"

    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "osint-d2"
    return Path.home() / ".config" / "osint-d2"


def get_user_env_file() -> Path:
    return get_user_config_dir() / ".env"


def _parse_env_lines(text: str) -> dict[str, str]:
    data: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            data[key] = value
    return data


def write_user_env_vars(values: dict[str, str]) -> Path:
    """Escribe/actualiza variables en el .env global del usuario."""

    env_path = get_user_env_file()
    env_path.parent.mkdir(parents=True, exist_ok=True)

    existing: dict[str, str] = {}
    if env_path.exists():
        try:
            existing = _parse_env_lines(env_path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}

    existing.update({k: v for k, v in values.items() if v is not None})

    lines = ["# OSINT-D2 user config (.env)"]
    for key in sorted(existing.keys()):
        lines.append(f"{key}={existing[key]}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return env_path


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
        # Orden: proyecto primero (dev), luego config global de usuario (PyInstaller).
        env_file=(".env", str(get_user_env_file())),
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
