"""Graph Exporter Adapter.

Transforms PersonEntity, SocialProfile, breaches and findings into
GraphExportModel (JSON Graph / Obsidian Canvas).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.domain.graph_models import GraphEdge, GraphExportModel, GraphNode
from core.domain.models import PersonEntity


class GraphExporter:
    """Adapts OSINT investigation results into interactive entity graphs."""

    @staticmethod
    def build_graph(
        person: PersonEntity,
        extra_entities: list[dict[str, Any]] | None = None,
    ) -> GraphExportModel:
        """Constructs nodes and edges from a PersonEntity."""
        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []
        seen_nodes: set[str] = set()

        def add_node(n_id: str, label: str, n_type: Any, props: dict[str, Any] | None = None) -> None:
            if n_id not in seen_nodes:
                seen_nodes.add(n_id)
                nodes.append(GraphNode(id=n_id, label=label, type=n_type, properties=props or {}))

        # 1. Target principal
        target_id = f"target:{person.target}"
        add_node(target_id, person.target, "Target", {"original_input": True})

        # 2. Perfiles sociales confirmados
        for prof in person.profiles:
            if not prof.exists:
                continue

            platform_id = f"platform:{prof.network_name.lower()}:{prof.username}"
            add_node(
                platform_id,
                f"{prof.network_name} (@{prof.username})",
                "Platform",
                {"url": prof.url, "bio": prof.bio},
            )
            edges.append(
                GraphEdge(
                    source=target_id,
                    target=platform_id,
                    type="HAS_PROFILE",
                    label="claimed profile",
                    properties={"url": prof.url},
                )
            )

            # Si el perfil incluye metadatos como emails o sitios externos
            meta = prof.metadata or {}
            for email in meta.get("other_emails", []):
                email_id = f"email:{email}"
                add_node(email_id, email, "Email")
                edges.append(GraphEdge(source=platform_id, target=email_id, type="EXPOSES_EMAIL"))

            for website in meta.get("other_websites", []):
                domain_id = f"domain:{website}"
                add_node(domain_id, website, "Domain")
                edges.append(GraphEdge(source=platform_id, target=domain_id, type="LINKS_TO"))

        # 3. Entidades extra deducidas (teléfono, colaborador, etc.)
        for item in extra_entities or []:
            e_type = item.get("type", "Identity")
            e_id = item.get("id") or f"{e_type.lower()}:{item.get('label')}"
            add_node(e_id, item.get("label", e_id), e_type, item.get("properties"))
            if item.get("source"):
                edges.append(
                    GraphEdge(
                        source=item["source"],
                        target=e_id,
                        type=item.get("relation", "ASSOCIATED_WITH"),
                        label=item.get("relation_label"),
                    )
                )

        metadata = {
            "generated_by": "OSINT-D2",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "target": person.target,
            "total_nodes": len(nodes),
            "total_edges": len(edges),
        }

        return GraphExportModel(nodes=nodes, edges=edges, metadata=metadata)

    @classmethod
    def export_json(cls, graph: GraphExportModel, output_path: str | Path) -> str:
        """Saves graph in JSON Graph format."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        content = graph.model_dump_json(indent=2)
        path.write_text(content, encoding="utf-8")
        return str(path)

    @classmethod
    def export_canvas(cls, graph: GraphExportModel, output_path: str | Path) -> str:
        """Saves graph in Obsidian Canvas format (.canvas)."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        canvas_dict = graph.to_obsidian_canvas()
        path.write_text(json.dumps(canvas_dict, indent=2, ensure_ascii=False), encoding="utf-8")
        return str(path)

    @classmethod
    def export_html(cls, graph: GraphExportModel, output_path: str | Path, title: str = "OSINT Graph") -> str:
        """Saves graph in standalone interactive HTML format."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        html = graph.to_interactive_html(title=title)
        path.write_text(html, encoding="utf-8")
        return str(path)

    @classmethod
    def export_graph_png(
        cls,
        graph: GraphExportModel,
        output_path: str | Path,
        title: str = "OSINT Intelligence Graph",
        width: int = 1600,
        height: int = 1100,
    ) -> str:
        """Renders the entity graph as a high-resolution PNG (Playwright/Chromium)."""
        from playwright.sync_api import sync_playwright

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        graph_html = graph.to_interactive_html(title=title)

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=2)
            page.set_content(graph_html, wait_until="networkidle")
            # Esperar a que la física del grafo se estabilice
            page.wait_for_timeout(3500)
            page.screenshot(path=str(path), full_page=False)
            browser.close()

        return str(path)
