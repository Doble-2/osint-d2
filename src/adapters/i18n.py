"""Interface strings for the dashboard and the investigation graph."""

from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

from core.domain.language import Language

_TEMPLATES_DIR = Path(__file__).parent / "templates"

# PyInstaller: templates are extracted under sys._MEIPASS/adapters/templates
_meipass = getattr(sys, "_MEIPASS", None)
if _meipass and (Path(str(_meipass)) / "adapters" / "templates").is_dir():
    _TEMPLATES_DIR = Path(str(_meipass)) / "adapters" / "templates"

TEMPLATES_DIR = _TEMPLATES_DIR
SUPPORTED_LANGUAGES = frozenset(language.value for language in Language)


@lru_cache(maxsize=8)
def load_translations(lang_code: str) -> dict[str, Any]:
    """Load one language's strings, falling back to English."""
    # A fixed list: lang_code can come from a URL, and it becomes part of a path.
    language = lang_code if lang_code in SUPPORTED_LANGUAGES else Language.default().value
    return json.loads((TEMPLATES_DIR / "i18n" / f"{language}.json").read_text(encoding="utf-8"))
