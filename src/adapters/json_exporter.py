"""Exportación JSON del agregado.

Por qué JSON:
- Interoperabilidad con otras herramientas OSINT y pipelines.
- Permite persistir evidencia/estado sin depender del render HTML/PDF.
"""

from __future__ import annotations

import json
from pathlib import Path

from core.domain.models import PersonEntity


def export_person_json(*, person: PersonEntity, output_path: Path) -> Path:
    """Exporta `PersonEntity` a JSON UTF-8 con formato estable."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = person.model_dump(mode="json")
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path
