#!/usr/bin/env bash
set -euo pipefail

# Builds a Linux dist/ folder using PyInstaller.
# Recommended: run inside a clean venv or container matching your target distro.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT_DIR"

if ! command -v python >/dev/null 2>&1; then
  echo "python not found" >&2
  exit 1
fi

python -m pip install --upgrade pip >/dev/null
python -m pip install "pyinstaller>=6.6" >/dev/null

pyinstaller -y packaging/pyinstaller/osint-d2.spec

echo "\nBuilt: $ROOT_DIR/dist/osint-d2/"
echo "Run:   $ROOT_DIR/dist/osint-d2/osint-d2 --help"
