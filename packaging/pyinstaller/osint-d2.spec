# PyInstaller spec for OSINT-D2
# Build:
#   pyinstaller -y packaging/pyinstaller/osint-d2.spec
#
# IMPORTANT: Playwright (Chromium) is NOT bundled — it would add ~150 MB to
# the binary.  After building, users must run:
#   playwright install chromium
# Graph PNG rendering and PDF graph pages will fail without it.

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

# ── Collect WeasyPrint & pydyf native libs + data files ──
# WeasyPrint dynamically loads Cairo/Pango via cffi; without collect_all the
# binary produces ImportError or OSError at PDF-export time.
from PyInstaller.utils.hooks import collect_all

wp_datas, wp_binaries, wp_hiddens = collect_all("weasyprint")
pydyf_datas, pydyf_binaries, pydyf_hiddens = collect_all("pydyf")

# Data files to bundle (templates + vendor assets)
# These paths are used by adapters/report_exporter.py via sys._MEIPASS fallbacks.
datas = [
    (str(ROOT / "src" / "adapters" / "templates"), "adapters/templates"),
    (str(ROOT / "src" / "adapters" / "templates" / "i18n"), "adapters/templates/i18n"),
    (str(ROOT / "src" / "adapters" / "templates" / "vendor"), "adapters/templates/vendor"),
] + wp_datas + pydyf_datas

binaries = wp_binaries + pydyf_binaries

hiddenimports = [
    # WeasyPrint pulls some modules dynamically
    "weasyprint",
    "weasyprint.text",
    "weasyprint.formatting_structure",
    "weasyprint.css",
    "pydyf",
] + wp_hiddens + pydyf_hiddens

# NOTE: tls-client uses native components; PyInstaller can work but may need
# platform-specific tweaks depending on distro/glibc.

from PyInstaller.building.build_main import Analysis, PYZ, EXE, COLLECT


a = Analysis(
    [ENTRY],
    pathex=[str(ROOT), str(ROOT / "src")],
    binaries=binaries,
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
