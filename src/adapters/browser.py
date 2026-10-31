"""The Chromium that Playwright uses for dashboard PDFs and graph images.

It's a large download that scans don't need, so it is installed on request.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path


def chromium_path() -> str:
    """Return where Playwright expects Chromium. Call it outside a running event loop."""

    async def probe() -> str:
        from playwright.async_api import async_playwright

        async with async_playwright() as playwright:
            return playwright.chromium.executable_path

    return asyncio.run(probe())


def chromium_installed() -> bool:
    try:
        return Path(chromium_path()).exists()
    except Exception:
        return False


def can_install_chromium() -> bool:
    # A PyInstaller build has no Python interpreter to run Playwright's installer.
    return not getattr(sys, "frozen", False)


def install_chromium() -> bool:
    """Download Chromium, showing the installer's own progress."""
    return subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"]).returncode == 0
