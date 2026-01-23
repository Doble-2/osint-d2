"""Carga de listas JSON (data-driven).

Soporta formatos tipo:
- Username: {"sites": [...]} (WhatsMyName wmn-data.json)
- Email:    {"sites": [...]} (email-data.json)

Nota legal:
- El repo no incluye datasets. El usuario puede descargarlos y apuntar a rutas
  locales mediante env vars o flags.
"""

from __future__ import annotations

import json
from pathlib import Path

from adapters.site_lists.models import EmailSitesFile, UsernameSitesFile


def load_username_sites(path: Path) -> UsernameSitesFile:
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    return UsernameSitesFile.model_validate(data)


def load_email_sites(path: Path) -> EmailSitesFile:
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    return EmailSitesFile.model_validate(data)
