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
