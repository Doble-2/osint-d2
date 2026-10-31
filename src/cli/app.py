"""The Typer application that every command registers on."""

from __future__ import annotations

import eval_type_backport
eval_type_backport.install_patch()  # Patch typing globally for PEP 604 unions

import typer

app = typer.Typer(
    name="osint-d2",
    no_args_is_help=False,
    # Tracebacks with locals would print API keys passed as arguments.
    pretty_exceptions_show_locals=False,
    help="Investigate public identity data for usernames, emails, and phone numbers.",
    epilog=(
        "Examples: osint-d2 scan johndoe  |  osint-d2 hunt -u johndoe -e john@example.com  |  "
        "osint-d2 agent johndoe  |  osint-d2 serve. "
        "Use only for lawful, authorized investigations."
    ),
)
