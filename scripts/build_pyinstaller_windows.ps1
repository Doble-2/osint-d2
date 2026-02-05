# Builds a Windows dist/ folder using PyInstaller.
# Run from PowerShell:
#   python -m venv .venv-build
#   .\.venv-build\Scripts\Activate.ps1
#   pip install -U pip
#   pip install -e .
#   .\scripts\build_pyinstaller_windows.ps1

$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot ".."))
Set-Location $Root

python -m pip install --upgrade pip | Out-Null
python -m pip install "pyinstaller>=6.6" | Out-Null

pyinstaller -y packaging/pyinstaller/osint-d2.spec

Write-Host "Built: $Root\dist\osint-d2\"
Write-Host "Run:   $Root\dist\osint-d2\osint-d2.exe --help"
