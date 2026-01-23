"""Script de ejecución.

Por qué existe:
- Permite ejecutar la CLI con `python -m main` durante desarrollo.
- Mantiene un entrypoint simple además del script de Poetry.
"""

from __future__ import annotations

from cli.main import run


def main() -> None:
    run()


if __name__ == "__main__":
    main()
