"""CLI UI components powered by Rich."""

from __future__ import annotations

from rich.align import Align
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from core.domain.models import AnalysisReport


def print_banner(console: Console) -> None:
    """Render the welcome banner for interactive sessions."""

    title = Text("OSINT-D2", style="bold bright_green")
    subtitle = Text("Identity intelligence • Correlation • AI", style="green3")
    body = Align.center(Text.assemble(title, "\n", subtitle), vertical="middle")
    console.print(Panel(body, border_style="bright_green", padding=(1, 4)))


def build_profiles_table() -> Table:
    """Create the Rich table used to display discovered profiles."""

    table = Table(title="Social Profiles", title_style="bright_green")
    table.add_column("Network", style="bright_green", no_wrap=True)
    table.add_column("Username", style="white")
    table.add_column("Exists", style="green3")
    table.add_column("URL", style="green")
    table.add_column("Error", style="red")
    return table


def build_breaches_table() -> Table:
    """Create the Rich table used to display HIBP breach results."""

    table = Table(title="Breaches (HIBP)", title_style="bright_green")
    table.add_column("Email", style="bright_green", no_wrap=True)
    table.add_column("Breach", style="white")
    table.add_column("Domain", style="white", no_wrap=True)
    table.add_column("Date", style="white", no_wrap=True)
    table.add_column("Records", style="white", justify="right", no_wrap=True)
    table.add_column("Data classes", style="green")
    table.add_column("Status", style="yellow", justify="right", no_wrap=True)
    table.add_column("Error", style="red")
    return table


def build_analysis_panel(report: AnalysisReport) -> Panel:
    """Render the AI analysis report in a Rich panel."""

    title = Text("AI Analysis", style="bold bright_green")
    body = Text()
    body.append(report.summary.strip() + "\n")

    # Only append highlights if they aren't already embedded in the summary.
    summary_lower = report.summary.lower()
    highlights_in_summary = (
        "highlight" in summary_lower
        or "puntos clave" in summary_lower
        or "hallazgos" in summary_lower
    )
    if report.highlights and not highlights_in_summary:
        body.append("\nHighlights:\n", style="bold bright_green")
        for h in report.highlights:
            body.append(f"- {h}\n")

    body.append(f"\nConfidence: {report.confidence:.2f}")
    if report.model:
        body.append(f"\nModel: {report.model}", style="dim")

    return Panel(body, title=title, border_style="bright_green")
