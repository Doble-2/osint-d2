import asyncio
from pathlib import Path
from core.config import AppSettings
from core.services.agent_engine import AgentEngine
from core.domain.language import Language
from adapters.graph_exporter import GraphExporter
from adapters.report_exporter import export_person_html

async def run_investigation():
    settings = AppSettings()

    print("=" * 70)
    print(">>> Example agent investigation <<<")
    print("=" * 70)

    def log_step(step):
        args_str = str(step.tool_args)
        if len(args_str) > 80:
            args_str = args_str[:80] + "..."
        print(f"  [Step {step.step_number}] Tool: {step.tool_name} | Args: {args_str}")

    engine = AgentEngine(
        settings=settings,
        enable_breach_check=False,
        on_step=log_step,
    )

    # Fictitious example data: replace it with a target you are authorized to investigate.
    objective = (
        'Investigate the subject Jane Doe. '
        'Usernames: "janedoe_example". '
        'Emails: "jane@example.com". '
        'Website: "https://example.com". '
        'Run scan_username and scan_email, then generate the final report.'
    )

    result = await engine.run(
        objective=objective,
        language=Language.SPANISH,
        max_steps=5,
        trust_anchors=["email:jane@example.com"]
    )

    reports_dir = Path("reports")
    reports_dir.mkdir(parents=True, exist_ok=True)

    # 1. Exportar HTML Dossier
    html_path = reports_dir / "example_dossier.html"
    try:
        export_person_html(person=result.person, output_path=html_path, language=Language.SPANISH)
        print(f"  [✓] HTML dossier: {html_path}")
    except Exception as e:
        print(f"  [!] HTML export failed: {e}")

    # 2. Exportar Grafo
    extra_nodes = [
        {"id": "identity:jane_doe", "label": "Jane Doe", "type": "Identity", "source": "target:janedoe_example", "relation": "LEGAL_NAME"},
        {"id": "email:jane@example.com", "label": "jane@example.com", "type": "Email", "source": "identity:jane_doe", "relation": "PERSONAL_EMAIL"},
        {"id": "domain:example.com", "label": "example.com", "type": "Domain", "source": "identity:jane_doe", "relation": "OWNS_DOMAIN"},
    ]
    graph = GraphExporter.build_graph(result.person, extra_entities=extra_nodes)
    canvas_file = reports_dir / "example.canvas"
    GraphExporter.export_canvas(graph, canvas_file)
    print(f"  [✓] Obsidian Canvas graph: {canvas_file}")

    print("\n" + "=" * 70)
    print(">>> Highlights and summary <<<")
    print("=" * 70)
    if result.person.analysis:
        print(f"Confidence: {result.person.analysis.confidence * 100:.1f}%\n")
        for h in result.person.analysis.highlights:
            print(f"  • {h}")
        print("\n" + result.person.analysis.summary)

if __name__ == "__main__":
    asyncio.run(run_investigation())
