"""Cargador de recursos/datasets (Fase 2).

Este módulo vive en `core/` porque:
- centraliza el *qué* datos necesitamos (manifest/listas) sin acoplarse a la CLI
- evita duplicar lógica de paths/descarga en adaptadores.

No incluye datasets en el repo; los descarga a `data/` (ignorarlo en git).
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx


SHERLOCK_MANIFEST_URL = (
    "https://raw.githubusercontent.com/sherlock-project/sherlock/master/"
    "sherlock_project/resources/data.json"
)


def _project_root() -> Path:
    # core/resources_loader.py -> core -> src -> <project_root>
    return Path(__file__).resolve().parents[2]


def get_default_list_path(filename: str) -> Path | None:
    """Busca un dataset por defecto en ubicaciones comunes.

    Orden:
    1) ./data/<filename> (en el project root)
    2) ../blackbird/data/<filename> (si existe al lado)
    3) ./<filename> (cwd)
    """

    root = _project_root()
    candidates = [
        root / "data" / filename,
        root.parent / "blackbird" / "data" / filename,
        Path.cwd() / filename,
    ]
    for p in candidates:
        if p.exists() and p.is_file():
            return p
    return None


def load_sherlock_data(*, refresh: bool = False, url: str = SHERLOCK_MANIFEST_URL) -> dict:
    """Carga el manifest de Sherlock (400+ sitios).

    Lógica:
    - Si existe `data/sherlock.json` y `refresh=False`, lo carga.
    - Si no existe (o refresh=True), lo descarga desde el repo oficial (raw).

    Devuelve:
    - dict con la estructura del manifest (con `$schema` si viene en el JSON).
    """

    root = _project_root()
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    out_path = data_dir / "sherlock.json"

    if out_path.exists() and not refresh:
        return json.loads(out_path.read_text(encoding="utf-8"))

    resp = httpx.get(
        url,
        timeout=30.0,
        headers={
            "User-Agent": "osint-d2/0.1 (+https://local)",
            "Accept": "application/json",
        },
        follow_redirects=True,
    )
    resp.raise_for_status()

    data = resp.json()
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return data
