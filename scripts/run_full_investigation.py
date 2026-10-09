import asyncio
from pathlib import Path
from core.config import AppSettings
from core.services.agent_engine import AgentEngine
from core.domain.language import Language
from core.domain.models import PersonEntity, SocialProfile, AnalysisReport
from adapters.graph_exporter import GraphExporter
from adapters.report_exporter import export_person_html
from adapters.activity_timeline import ActivityTimeline

async def run_investigation():
    settings = AppSettings()
    
    print("=" * 70)
    print(">>> LANZANDO AGENTE OSINT FORENSE MULTI-VECTOR <<<")
    print("=" * 70)
    
    def log_step(step):
        args_str = str(step.tool_args)
        if len(args_str) > 80: args_str = args_str[:80] + "..."
        print(f"  [Paso {step.step_number}] Herramienta: {step.tool_name} | Args: {args_str}")

    engine = AgentEngine(
        settings=settings,
        enable_breach_check=False,
        on_step=log_step,
    )

    objective = (
        'Investigación integral del objetivo Ángel Calderón Rodríguez. '
        'Vectores: Usernames "Doble-2", "angelcaldev", "DobleVneko". '
        'Emails: "angel@angelcalderon.dev", "acalderon@fospuca.com". '
        'Teléfono: "+584241922882". '
        'Web: "https://angelcalderon.dev". '
        'Ejecuta scan_username, scan_email, scan_phone y genera el reporte final.'
    )

    result = await engine.run(
        objective=objective,
        language=Language.SPANISH,
        max_steps=5,
        trust_anchors=["https://github.com/Doble-2"]
    )

    reports_dir = Path("reports")
    reports_dir.mkdir(parents=True, exist_ok=True)

    # 1. Exportar HTML Dossier
    html_path = reports_dir / "angel_calderon_dossier.html"
    try:
        export_person_html(person=result.person, output_path=html_path, language=Language.SPANISH)
        print(f"  [✓] Reporte Dossier HTML: {html_path}")
    except Exception as e:
        print(f"  [!] Error exportando HTML: {e}")

    # 2. Exportar Grafo
    extra_nodes = [
        {"id": "identity:angel_calderon", "label": "Ángel Calderón Rodríguez", "type": "Identity", "source": "target:Doble-2", "relation": "LEGAL_NAME"},
        {"id": "email:angel@angelcalderon.dev", "label": "angel@angelcalderon.dev (Personal)", "type": "Email", "source": "identity:angel_calderon", "relation": "PERSONAL_EMAIL"},
        {"id": "email:acalderon@fospuca.com", "label": "acalderon@fospuca.com (Fospuca Corp)", "type": "Email", "source": "identity:angel_calderon", "relation": "WORK_EMAIL"},
        {"id": "phone:+584241922882", "label": "+58 424-192-2882 (Movistar / WhatsApp)", "type": "Phone", "source": "identity:angel_calderon", "relation": "MOBILE_PHONE"},
        {"id": "domain:angelcalderon.dev", "label": "angelcalderon.dev (Portfolio)", "type": "Domain", "source": "identity:angel_calderon", "relation": "OWNS_DOMAIN"},
        {"id": "colleague:raishid", "label": "David Raishid (fededav)", "type": "Colleague", "source": "domain:angelcalderon.dev", "relation": "COLLABORATES_WITH"}
    ]
    graph = GraphExporter.build_graph(result.person, extra_entities=extra_nodes)
    canvas_file = reports_dir / "angel_calderon_master.canvas"
    GraphExporter.export_canvas(graph, canvas_file)
    print(f"  [✓] Grafo Obsidian Canvas: {canvas_file}")

    print("\n" + "=" * 70)
    print(">>> HIGHLIGHTS Y RESUMEN FORENSE FINAL <<<")
    print("=" * 70)
    if result.person.analysis:
        print(f"Confianza: {result.person.analysis.confidence * 100:.1f}%\n")
        for h in result.person.analysis.highlights:
            print(f"  • {h}")
        print("\n" + result.person.analysis.summary)

if __name__ == "__main__":
    asyncio.run(run_investigation())
