import json
from pathlib import Path
from adapters.graph_exporter import GraphExporter
from core.domain.models import PersonEntity, SocialProfile


def test_graph_exporter_build_and_export_canvas(tmp_path: Path):
    prof1 = SocialProfile(
        url="https://github.com/Doble-2",
        username="Doble-2",
        network_name="GitHub",
        exists=True,
        metadata={"other_websites": ["https://angelcalderon.dev"]},
    )
    prof2 = SocialProfile(
        url="https://gitlab.com/Doble-2",
        username="Doble-2",
        network_name="GitLab",
        exists=True,
    )
    prof_unconfirmed = SocialProfile(
        url="https://fake.com/Doble-2",
        username="Doble-2",
        network_name="FakeNet",
        exists=False,
    )

    person = PersonEntity(target="Doble-2", profiles=[prof1, prof2, prof_unconfirmed])

    extra = [
        {
            "id": "phone:+584241922882",
            "label": "+58 424-192-2882",
            "type": "Phone",
            "source": "platform:github:doble-2",
            "relation": "EXPOSES_PHONE",
        },
        {
            "id": "colleague:raishid",
            "label": "Federico David (raishid)",
            "type": "Colleague",
            "source": "domain:https://angelcalderon.dev",
            "relation": "COLLABORATES_WITH",
        },
    ]

    graph = GraphExporter.build_graph(person, extra_entities=extra)

    assert len(graph.nodes) >= 5
    assert len(graph.edges) >= 4

    # Exportar Canvas
    canvas_file = tmp_path / "investigation.canvas"
    GraphExporter.export_canvas(graph, canvas_file)
    assert canvas_file.exists()

    canvas_data = json.loads(canvas_file.read_text(encoding="utf-8"))
    assert "nodes" in canvas_data
    assert "edges" in canvas_data
    assert len(canvas_data["nodes"]) == len(graph.nodes)
