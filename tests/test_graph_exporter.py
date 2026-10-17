import json
from pathlib import Path
from adapters.graph_exporter import GraphExporter
from core.domain.models import PersonEntity, SocialProfile


def test_graph_exporter_build_and_export_canvas(tmp_path: Path):
    prof1 = SocialProfile(
        url="https://github.com/testuser",
        username="testuser",
        network_name="GitHub",
        exists=True,
        metadata={"other_websites": ["https://example.com/portfolio"]},
    )
    prof2 = SocialProfile(
        url="https://gitlab.com/testuser",
        username="testuser",
        network_name="GitLab",
        exists=True,
    )
    prof_unconfirmed = SocialProfile(
        url="https://fake.com/testuser",
        username="testuser",
        network_name="FakeNet",
        exists=False,
    )

    person = PersonEntity(target="testuser", profiles=[prof1, prof2, prof_unconfirmed])

    extra = [
        {
            "id": "phone:+12125551234",
            "label": "+1 212-555-1234",
            "type": "Phone",
            "source": "platform:github:testuser",
            "relation": "EXPOSES_PHONE",
        },
        {
            "id": "colleague:johndoe",
            "label": "John Doe (johndoe)",
            "type": "Colleague",
            "source": "domain:https://example.com/portfolio",
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
