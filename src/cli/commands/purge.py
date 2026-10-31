"""`purge`: delete saved reports."""

from __future__ import annotations

import typer
from rich.markup import escape

from adapters.report_store import find_reports
from cli.app import app
from cli.shared import out_console


@app.command(help="Delete saved reports by target, by age, or both.")
def purge(
    target: str | None = typer.Option(None, "--target", "-t", help="Exact target of the investigation.", show_default=False),
    older_than: int | None = typer.Option(None, "--older-than", min=0, help="Only reports older than this many days.", show_default=False),
    dry_run: bool = typer.Option(False, "--dry-run", help="List the files without deleting them."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Delete without asking for confirmation."),
) -> None:
    if target is None and older_than is None:
        raise typer.BadParameter("Pass --target, --older-than, or both.")

    paths = find_reports(target=target, older_than_days=older_than)
    if not paths:
        out_console.print("No matching reports.")
        return
    for path in paths:
        out_console.print(escape(str(path)), highlight=False)
    if dry_run:
        return
    if not yes:
        typer.confirm(f"Delete {len(paths)} file(s)? This cannot be undone.", abort=True)
    for path in paths:
        path.unlink(missing_ok=True)
    out_console.print(f"Deleted {len(paths)} file(s).")
