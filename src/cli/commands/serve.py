"""`serve`: the local web dashboard."""

from __future__ import annotations


import typer

from cli.ui_components import print_banner
from cli.app import app
from cli.shared import (
    out_console,
)


@app.command(name="serve", help="Launch the real-time web dashboard (FastAPI + WebSockets).")
def serve(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host interface to bind to."),
    port: int = typer.Option(8000, "--port", "-p", help="Port number for the web server."),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload for development."),
) -> None:
    """Starts the OSINT-D2 live intelligence web server."""
    import uvicorn
    from adapters.web_server import app as web_app

    console = out_console
    print_banner(console)
    console.print(f"[bold cyan]Starting Live Intelligence Dashboard at:[/bold cyan] [underline green]http://{host}:{port}[/underline green]")
    if host not in ("127.0.0.1", "localhost", "::1"):
        console.print(
            "[bold yellow]Warning:[/bold yellow] this is a local tool with no authentication. Anyone who "
            f"can reach {host}:{port} can start investigations and download dossiers."
        )
    console.print("[dim]Press Ctrl+C to terminate the web server.[/dim]\n")
    uvicorn.run(web_app, host=host, port=port, reload=reload)
