"""Development entry point (without Poetry).

Allows running the CLI with `python main.py` when not using an editable
install.  The code lives under ``src/`` (src-layout), so this wrapper
adds ``src/`` to ``sys.path`` before importing the real entry point.

For PyInstaller / installed builds, ``src/main.py`` is used directly.
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    project_root = Path(__file__).resolve().parent
    src = project_root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))

    # Workaround for UnicodeEncodeError on Windows terminals/CI.
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

    from cli.main import run  # noqa: PLC0415

    run()


if __name__ == "__main__":
    main()
