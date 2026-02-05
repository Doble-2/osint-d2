#!/usr/bin/env bash
set -euo pipefail

# Builds a macOS dist/ folder using PyInstaller.
# Requires Homebrew libs for WeasyPrint (optional but recommended).

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if command -v brew >/dev/null 2>&1; then
  # Best-effort: provide cairo/pango/gdk-pixbuf to enable PDF export.
  brew install cairo pango gdk-pixbuf libffi shared-mime-info || true
fi

python -m pip install --upgrade pip >/dev/null
python -m pip install "pyinstaller>=6.6" >/dev/null

pyinstaller -y packaging/pyinstaller/osint-d2.spec

echo "\nBuilt: $ROOT_DIR/dist/osint-d2/"
echo "Run:   $ROOT_DIR/dist/osint-d2/osint-d2 --help"
