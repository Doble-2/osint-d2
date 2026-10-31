"""CLI entry point (Typer + Rich).

Commands live in ``cli.commands``. This layer orchestrates; scraping and business
rules stay in ``core`` and ``adapters``. I/O-heavy work runs in async helpers
through ``asyncio.run(...)``, so Typer commands remain synchronous.
"""

from __future__ import annotations

import errno
import os
import signal
import sys
from contextlib import suppress

import click
import typer
from rich.markup import escape
from typer import rich_utils

from cli.app import app
from cli.commands import agent, phone, scanning, serve  # noqa: F401  (registers the commands)
from cli.commands.wizard import wizard
from cli.doctor import app as doctor_app
from cli.shared import err_console
from core import __version__

app.add_typer(doctor_app, name="doctor")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"osint-d2 {__version__}")
        raise typer.Exit()


try:
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
except Exception:
    pass


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the version and exit.",
    ),
) -> None:
    if ctx.invoked_subcommand is None:
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            typer.echo(ctx.get_help())
            raise typer.Exit(code=0)
        wizard()


def _dispatch() -> int | None:
    # Non-standalone mode returns control here, so run() sets every exit code.
    return app(standalone_mode=False)


def run() -> None:
    try:
        exit_code = _dispatch()
    except click.ClickException as exc:
        rich_utils.rich_format_error(exc)
        raise SystemExit(exc.exit_code)
    except (click.Abort, KeyboardInterrupt):
        err_console.print("\n[yellow]Interrupted.[/yellow]")
        raise SystemExit(130)
    except BrokenPipeError:
        with suppress(Exception):
            sys.stdout.flush()
        with suppress(Exception):
            fd = os.open(os.devnull, os.O_WRONLY)
            os.dup2(fd, sys.stdout.fileno())
            os.close(fd)
        raise SystemExit(0)
    except OSError as exc:
        if exc.errno == errno.EPIPE:
            raise SystemExit(0)
        _report_unexpected_error(exc)
    except Exception as exc:
        _report_unexpected_error(exc)
    raise SystemExit(exit_code if isinstance(exit_code, int) else 0)


def _report_unexpected_error(exc: Exception) -> None:
    """Show one clear line; a traceback could expose arguments such as API keys."""
    if os.environ.get("OSINT_D2_DEBUG"):
        raise exc
    err_console.print(f"[red]Error:[/red] {escape(str(exc) or type(exc).__name__)}")
    err_console.print("[dim]Set OSINT_D2_DEBUG=1 to see the full traceback.[/dim]")
    raise SystemExit(1)


if __name__ == "__main__":
    run()
