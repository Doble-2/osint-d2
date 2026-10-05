"""Graph models for entity resolution and visual investigation (Obsidian Canvas / JSON Graph).
"""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


class GraphNode(BaseModel):
    """Representa un nodo en el grafo de investigación."""

    id: str = Field(..., description="Identificador único del nodo.")
    label: str = Field(..., description="Etiqueta visible del nodo.")
    type: Literal[
        "Target", "Platform", "Identity", "Phone", "Email", "Colleague", "Breach", "Domain"
    ] = Field(..., description="Categoría visual y analítica del nodo.")
    properties: dict[str, Any] = Field(
        default_factory=dict, description="Metadatos adicionales del nodo."
    )


class GraphEdge(BaseModel):
    """Representa una arista o relación dirigida entre dos nodos."""

    id: str | None = Field(default=None, description="Identificador opcional de la arista.")
    source: str = Field(..., description="ID del nodo de origen.")
    target: str = Field(..., description="ID del nodo destino.")
    type: str = Field(..., description="Tipo semántico de relación (ej. 'HAS_PROFILE', 'USES_PHONE').")
    label: str | None = Field(default=None, description="Etiqueta visible de la relación.")
    properties: dict[str, Any] = Field(
        default_factory=dict, description="Metadatos de la relación."
    )


class GraphExportModel(BaseModel):
    """Modelo completo exportable compatible con JSON Graph y Obsidian Canvas."""

    nodes: list[GraphNode] = Field(default_factory=list, description="Lista de nodos.")
    edges: list[GraphEdge] = Field(default_factory=list, description="Lista de aristas.")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Metadatos globales de la investigación."
    )

    def to_obsidian_canvas(self) -> dict[str, Any]:
        """Convierte la estructura al formato nativo .canvas de Obsidian."""
        canvas_nodes = []
        canvas_edges = []

        # Color mapping para Obsidian Canvas (1: red, 2: orange, 3: yellow, 4: green, 5: cyan, 6: purple)
        type_colors = {
            "Target": "1",
            "Identity": "2",
            "Platform": "5",
            "Email": "3",
            "Phone": "4",
            "Colleague": "6",
            "Breach": "1",
            "Domain": "5",
        }

        # Grid layout básico en 2D
        cols = 4
        spacing_x = 280
        spacing_y = 160

        for i, node in enumerate(self.nodes):
            row = i // cols
            col = i % cols
            canvas_nodes.append({
                "id": node.id,
                "x": col * spacing_x,
                "y": row * spacing_y,
                "width": 240,
                "height": 100,
                "color": type_colors.get(node.type, "0"),
                "type": "text",
                "text": f"### [{node.type}] {node.label}\nID: `{node.id}`",
            })

        for i, edge in enumerate(self.edges):
            canvas_edges.append({
                "id": edge.id or f"edge_{i}",
                "fromNode": edge.source,
                "toNode": edge.target,
                "label": edge.label or edge.type,
            })

        return {"nodes": canvas_nodes, "edges": canvas_edges}

    def to_interactive_html(self, title: str = "OSINT Intelligence Graph") -> str:
        """Generates a standalone, dark-themed, high-resolution interactive HTML graph (Palantir/Maltego style)."""
        import json

        nodes_data = []
        edges_data = []

        type_groups = {
            "Target": "target",
            "Identity": "identity",
            "Phone": "phone",
            "Email": "email",
            "Platform": "social",
            "Domain": "domain",
            "Colleague": "colleague",
            "Breach": "breach",
        }

        for n in self.nodes:
            group = type_groups.get(n.type, "social")
            nodes_data.append({
                "id": n.id,
                "label": n.label,
                "group": group,
                "shape": "dot" if n.type == "Target" else "box",
                "info": n.properties.get("bio") or n.properties.get("url") or f"Tipo: {n.type}",
            })

        for e in self.edges:
            edges_data.append({
                "from": e.source,
                "to": e.target,
                "label": e.label or e.type,
                "arrows": "to",
            })

        return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>{title}</title>
  <script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
  <style>
    body, html {{ width: 100%; height: 100%; margin: 0; padding: 0; overflow: hidden; background: #0a0d14; font-family: -apple-system, sans-serif; color: #fff; }}
    #header {{ position: absolute; top: 12px; left: 12px; z-index: 10; background: rgba(16, 22, 34, 0.85); backdrop-filter: blur(10px); padding: 10px 16px; border-radius: 12px; border: 1px solid #1e293b; }}
    #network {{ width: 100%; height: 100%; }}
  </style>
</head>
<body>
  <div id="header"><h3>{title}</h3></div>
  <div id="network"></div>
  <script>
    var nodes = new vis.DataSet({json.dumps(nodes_data)});
    var edges = new vis.DataSet({json.dumps(edges_data)});
    var container = document.getElementById('network');
    new vis.Network(container, {{ nodes: nodes, edges: edges }}, {{
      physics: {{ solver: 'forceAtlas2Based', forceAtlas2Based: {{ springLength: 140 }} }},
      interaction: {{ hover: true }}
    }});
  </script>
</body>
</html>"""

