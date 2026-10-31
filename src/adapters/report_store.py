"""Finds and deletes saved dossiers, which hold personal data about third parties."""

from __future__ import annotations

import re
import time
from pathlib import Path

from core.services.identity_pipeline import sanitize_target_for_filename

REPORTS_DIR = Path("reports")

# Only what OSINT-D2 writes, so a purge never touches anything else in the folder.
_REPORT_SUFFIXES = frozenset({".pdf", ".html", ".json", ".canvas", ".svg", ".png"})


def _belongs_to(path: Path, target: str) -> bool:
    # Exact shape, not a prefix: purging "ana" must not delete "ana_maria".
    name = re.escape(sanitize_target_for_filename(target))
    return re.fullmatch(rf"{name}(_[0-9a-f]{{8}})?(_graph|_grafo|_dossier)?", path.stem) is not None


def find_reports(
    *,
    reports_dir: Path = REPORTS_DIR,
    target: str | None = None,
    older_than_days: int | None = None,
) -> list[Path]:
    """Return saved reports matching every given filter."""
    if not reports_dir.is_dir():
        return []
    cutoff = None if older_than_days is None else time.time() - older_than_days * 86_400
    return sorted(
        path for path in reports_dir.iterdir()
        if path.suffix.lower() in _REPORT_SUFFIXES
        and path.is_file()
        and not path.is_symlink()
        and (target is None or _belongs_to(path, target))
        and (cutoff is None or path.stat().st_mtime < cutoff)
    )


def purge_expired(retention_days: int | None, *, reports_dir: Path = REPORTS_DIR) -> int:
    """Delete reports past the retention period; no period means keep everything."""
    if retention_days is None:
        return 0
    expired = find_reports(reports_dir=reports_dir, older_than_days=retention_days)
    for path in expired:
        path.unlink(missing_ok=True)
    return len(expired)
