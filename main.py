"""Entry point de desarrollo (sin Poetry).

Permite ejecutar la CLI con:
- `python -m main ...`

Motivo:
- El código vive en `src/` (layout tipo "src"), así que si no estás usando
  Poetry/pip (editable install), Python no encuentra `cli`, `core`, etc.
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    project_root = Path(__file__).resolve().parent
    src = project_root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))

    from cli.main import run  # noqa: PLC0415

    run()


if __name__ == "__main__":
    main()
