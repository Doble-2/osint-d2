"""Modelos para listas de sitios (data-driven).

Idea:
- En vez de crear 600 clases Scanner, leemos un JSON (p.ej. WhatsMyName) y
  ejecutamos un motor genérico.

Importante:
- No incluimos datasets en el repo por defecto. El usuario puede apuntar a una
  ruta local con `--username-sites-path` / `--email-sites-path`.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class UsernameSite(BaseModel):
    name: str = Field(..., min_length=1)
    uri_check: str = Field(..., min_length=1)
    e_code: int = Field(..., ge=100, le=599)
    e_string: str = Field(..., min_length=1)

    m_string: str | None = None
    m_code: int | None = Field(default=None, ge=100, le=599)

    cat: str | None = None


class EmailSite(BaseModel):
    name: str = Field(..., min_length=1)
    uri_check: str = Field(..., min_length=1)

    method: str = Field(default="GET")
    data: str | None = None
    headers: dict[str, Any] | None = None

    e_code: int = Field(..., ge=100, le=599)
    e_string: str = Field(..., min_length=1)

    m_string: str | None = None
    m_code: int | None = Field(default=None, ge=100, le=599)

    cat: str | None = None
    input_operation: str | None = None


class UsernameSitesFile(BaseModel):
    sites: list[UsernameSite] = Field(default_factory=list)


class EmailSitesFile(BaseModel):
    sites: list[EmailSite] = Field(default_factory=list)
