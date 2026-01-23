"""Componentes de UI para CLI (Rich).

Por qué separar componentes:
- Evita mezclar lógica de comandos con detalles visuales.
- Permite reutilizar tablas/paneles en múltiples comandos.

Nota: se implementará cuando tengamos resultados reales de scanners.
"""

from __future__ import annotations

from rich.align import Align
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from core.domain.models import AnalysisReport


def print_banner(console: Console) -> None:
    """Imprime el banner de bienvenida.

    Por qué aquí:
    - Evita dependencias circulares (main <-> doctor).
    - Permite desactivar banner en modos no interactivos (JSON/pipelines).
    """

    title = Text("OSINT-D2", style="bold cyan")
    subtitle = Text("Investigación de identidades • Correlación • IA", style="dim")
    body = Align.center(Text.assemble(title, "\n", subtitle), vertical="middle")
    console.print(Panel(body, border_style="cyan", padding=(1, 4)))


def build_profiles_table() -> Table:
    """Crea una tabla Rich para perfiles (placeholder)."""

    table = Table(title="Social Profiles")
    table.add_column("Network", style="cyan", no_wrap=True)
    table.add_column("Username", style="white")
    table.add_column("Exists", style="green")
    table.add_column("URL", style="magenta")
    table.add_column("Error", style="red")
    return table


def build_analysis_panel(report: AnalysisReport) -> Panel:
    """Panel para presentar el `AnalysisReport` (IA)."""

    title = Text("Análisis IA", style="bold yellow")
    body = Text()
    body.append(report.summary.strip() + "\n\n")
    if report.highlights:
        body.append("Highlights:\n", style="bold")
        for h in report.highlights:
            body.append(f"- {h}\n")
    body.append(f"\nConfianza: {report.confidence:.2f}")
    if report.model:
        body.append(f"\nModelo: {report.model}", style="dim")

    return Panel(body, title=title, border_style="yellow")
