"""`serve`: the local web dashboard."""

from __future__ import annotations


import sys

import typer
from rich.console import Console

from adapters.browser import can_install_chromium, chromium_installed, install_chromium
from adapters.report_store import purge_expired
from core.config import AppSettings
from cli.ui_components import print_banner
from cli.app import app
from cli.shared import (
    out_console,
)


def _offer_chromium(console: Console) -> None:
    """Dashboard PDFs need Chromium; ask here because the server can't ask later."""
    if chromium_installed() or not can_install_chromium():
        return
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        console.print("[yellow]Chromium is missing, so dashboard PDFs are off.[/yellow] Run: osint-d2 doctor install-browser")
        return
    if typer.confirm("Dashboard PDFs need Chromium, a large download. Install it now?", default=True):
        if not install_chromium():
            console.print("[yellow]Chromium could not be installed, so dashboard PDFs are off.[/yellow]")


@app.command(name="serve", help="Launch the real-time web dashboard (FastAPI + WebSockets).")
def serve(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host interface to bind to."),
    port: int = typer.Option(8000, "--port", "-p", help="Port number for the web server."),
) -> None:
    """Starts the OSINT-D2 live intelligence web server."""
    import uvicorn
    from adapters.web_server import app as web_app

    console = out_console
    print_banner(console)
    purged = purge_expired(AppSettings().report_retention_days)
    if purged:
        console.print(f"[dim]Deleted {purged} report file(s) past the retention period.[/dim]")
    _offer_chromium(console)
    console.print(f"[bold cyan]Starting Live Intelligence Dashboard at:[/bold cyan] [underline green]http://{host}:{port}[/underline green]")
    if host not in ("127.0.0.1", "localhost", "::1"):
        console.print(
            "[bold yellow]Warning:[/bold yellow] this is a local tool with no authentication. Anyone who "
            f"can reach {host}:{port} can start investigations and download dossiers."
        )
    console.print("[dim]Press Ctrl+C to terminate the web server.[/dim]\n")
    uvicorn.run(web_app, host=host, port=port)
