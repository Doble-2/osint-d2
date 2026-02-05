# PyInstaller spec for OSINT-D2
# Build:
#   pyinstaller -y packaging/pyinstaller/osint-d2.spec

from __future__ import annotations

from pathlib import Path

block_cipher = None

_spec_dir = Path(globals().get("SPECPATH", Path.cwd())).resolve()

# When invoked by PyInstaller, SPECPATH points to the directory containing this spec
# (e.g. <repo>/packaging/pyinstaller). When SPECPATH is not provided, fall back to cwd.
ROOT = (_spec_dir / ".." / "..").resolve()
if not (ROOT / "pyproject.toml").exists():
    ROOT = _spec_dir

# Entry point: root main.py injects src/ into sys.path (important for src-layout)
ENTRY = str(ROOT / "main.py")

# Data files to bundle (templates)
# These paths are used by adapters/report_exporter.py via sys._MEIPASS fallbacks.
datas = [
    (str(ROOT / "src" / "adapters" / "templates"), "adapters/templates"),
    (str(ROOT / "src" / "templates"), "templates"),
]

hiddenimports = [
    # WeasyPrint pulls some modules dynamically
    "weasyprint",
    "weasyprint.text",
    "weasyprint.formatting_structure",
    "weasyprint.css",
    "pydyf",
]

# NOTE: tls-client uses native components; PyInstaller can work but may need
# platform-specific tweaks depending on distro/glibc.

from PyInstaller.building.build_main import Analysis, PYZ, EXE, COLLECT


a = Analysis(
    [ENTRY],
    pathex=[str(ROOT), str(ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="osint-d2",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="osint-d2",
)
