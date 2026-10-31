"""Interface strings for the dashboard and the investigation graph."""

from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

_TEMPLATES_DIR = Path(__file__).parent / "templates"

# PyInstaller: templates are extracted under sys._MEIPASS/adapters/templates
_meipass = getattr(sys, "_MEIPASS", None)
if _meipass and (Path(str(_meipass)) / "adapters" / "templates").is_dir():
    _TEMPLATES_DIR = Path(str(_meipass)) / "adapters" / "templates"

TEMPLATES_DIR = _TEMPLATES_DIR


@lru_cache(maxsize=8)
def load_translations(lang_code: str) -> dict[str, Any]:
    """Load one language's strings, falling back to English."""
    i18n_file = TEMPLATES_DIR / "i18n" / f"{lang_code}.json"
    if not i18n_file.exists():
        i18n_file = TEMPLATES_DIR / "i18n" / "en.json"
    return json.loads(i18n_file.read_text(encoding="utf-8"))
