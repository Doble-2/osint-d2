"""Script de ejecución.

Por qué existe:
- Permite ejecutar la CLI con `python -m main` durante desarrollo.
- Mantiene un entrypoint simple además del script de Poetry.
"""

from __future__ import annotations

import sys

# Workaround for UnicodeEncodeError on Windows terminals/CI (cp1252 vs utf-8).
# Especially important for PyInstaller builds where PYTHONIOENCODING might be unset.
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from cli.main import run


def main() -> None:
    run()


if __name__ == "__main__":
    main()
