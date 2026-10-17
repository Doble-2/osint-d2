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
        "Target", "Platform", "Identity", "Phone", "Email", "Colleague", "Breach",
        "Domain", "Noise", "Finding"
    ] = Field(..., description="Categoría visual y analítica del nodo.")
    correlation: float | None = Field(
        default=None,
        description="Índice de correlación 0.0-1.0 con el objetivo (None si no aplica).",
    )
    evidence: str | None = Field(
        default=None,
        description="Evidencia concreta que sustenta este nodo (bio, URL, métrica, score).",
    )
    data: dict[str, str] = Field(
        default_factory=dict,
        description="Datos estructurados del hallazgo (bio, ubicación, seguidores, repos...).",
    )
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
        """Generates a standalone, dark-themed interactive HTML graph (Palantir/Maltego style).

        Uses a hierarchical radial layout (not chaotic force physics) so the
        target sits center, verified assets orbit close, and platforms fan out.
        Labels are short and information-dense.
        """
        import json

        nodes_data = []
        edges_data = []

        # Nivel jerárquico: define la órbita visual de cada tipo de entidad.
        level_map = {
            "Target": 0,
            "Identity": 1,
            "Phone": 1,
            "Email": 1,
            "Domain": 1,
            "Finding": 1,
            "Platform": 2,
            "Colleague": 2,
            "Breach": 2,
            "Noise": 3,
        }

        type_groups = {
            "Target": "target",
            "Identity": "identity",
            "Phone": "phone",
            "Email": "email",
            "Platform": "platform",
            "Domain": "domain",
            "Colleague": "colleague",
            "Breach": "breach",
            "Noise": "noise",
            "Finding": "finding",
        }

        for n in self.nodes:
            group = type_groups.get(n.type, "platform")
            # Tooltip rico: evidencia + índice de correlación
            tip_parts = []
            if n.correlation is not None:
                tip_parts.append(f"Correlacion: {int(float(n.correlation) * 100)}%")
            if n.evidence:
                tip_parts.append(n.evidence)
            if n.properties.get("url"):
                tip_parts.append(f"URL: {n.properties['url']}")
            tip_parts.append(f"Tipo: {n.type}")
            nodes_data.append({
                "id": n.id,
                "label": n.label,
                "group": group,
                "level": level_map.get(n.type, 2),
                "shape": "hexagon" if n.type == "Target" else "box",
                "title": "\n".join(tip_parts),
                "correlation": n.correlation,
            })

        for e in self.edges:
            edges_data.append({
                "from": e.source,
                "to": e.target,
                "label": "" if e.type in ("SCANNED",) else (e.label or e.type),
                "arrows": "to",
                "dashes": e.type in ("CONCLUSION", "COLLABORATES_WITH", "COLABORA"),
            })

        return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>{title}</title>
  <script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
  <style>
    body, html {{ width: 100%; height: 100%; margin: 0; padding: 0; overflow: hidden; background: #0a0d14; font-family: -apple-system, BlinkMacSystemFont, sans-serif; color: #fff; }}
    #header {{ position: absolute; top: 14px; left: 14px; z-index: 10; background: rgba(16, 22, 34, 0.9); backdrop-filter: blur(10px); padding: 12px 18px; border-radius: 12px; border: 1px solid #1e293b; }}
    #header h3 {{ margin: 0; font-size: 14px; color: #00f0ff; letter-spacing: 0.5px; }}
    #header p {{ margin: 4px 0 0 0; font-size: 10px; color: #64748b; }}
    #network {{ width: 100%; height: 100%; }}
    #legend {{ position: absolute; bottom: 14px; left: 14px; z-index: 10; background: rgba(16, 22, 34, 0.9); backdrop-filter: blur(10px); padding: 10px 14px; border-radius: 10px; border: 1px solid #1e293b; font-size: 10px; color: #94a3b8; display: flex; gap: 14px; flex-wrap: wrap; max-width: 60%; }}
    .lg {{ display: flex; align-items: center; gap: 5px; }}
    .dot {{ width: 8px; height: 8px; border-radius: 50%; }}
    .stats {{ position: absolute; top: 14px; right: 14px; z-index: 10; background: rgba(16, 22, 34, 0.9); backdrop-filter: blur(10px); padding: 10px 16px; border-radius: 10px; border: 1px solid #1e293b; font-size: 11px; font-family: monospace; color: #94a3b8; }}
  </style>
</head>
<body>
  <div id="header">
    <h3>{title}</h3>
    <p>Correlación de entidades &mdash; solo hallazgos con valor de inteligencia</p>
  </div>
  <div class="stats">
    NODOS: <span style="color:#00f0ff;font-weight:bold;">{len(nodes_data)}</span><br>
    RELACIONES: <span style="color:#00f0ff;font-weight:bold;">{len(edges_data)}</span>
  </div>
  <div id="legend">
    <span class="lg"><span class="dot" style="background:#ff0055"></span>Target</span>
    <span class="lg"><span class="dot" style="background:#ffaa00"></span>Identidad</span>
    <span class="lg"><span class="dot" style="background:#00ff88"></span>Tel&eacute;fono</span>
    <span class="lg"><span class="dot" style="background:#ffd000"></span>Correo</span>
    <span class="lg"><span class="dot" style="background:#00f0ff"></span>Plataforma</span>
    <span class="lg"><span class="dot" style="background:#bd00ff"></span>Colaborador</span>
    <span class="lg"><span class="dot" style="background:#38bdf8"></span>Conclusi&oacute;n</span>
    <span class="lg"><span class="dot" style="background:#475569"></span>Hom&oacute;nimo/Descartado</span>
  </div>
  <div id="network"></div>
  <script>
    var nodes = new vis.DataSet({json.dumps(nodes_data, ensure_ascii=False)});
    var edges = new vis.DataSet({json.dumps(edges_data, ensure_ascii=False)});
    var container = document.getElementById('network');

    var options = {{
      layout: {{
        hierarchical: {{
          enabled: true,
          direction: 'UD',
          sortMethod: 'directed',
          levelSeparation: 190,
          nodeSpacing: 210,
          treeSpacing: 220,
          blockShifting: true,
          edgeMinimization: true,
          parentCentralization: true
        }}
      }},
      physics: {{ enabled: false }},
      nodes: {{
        shape: 'box',
        margin: {{ top: 10, bottom: 10, left: 14, right: 14 }},
        borderWidth: 2,
        font: {{ color: '#e2e8f0', size: 13, face: '-apple-system, sans-serif', multi: 'html' }},
        shadow: {{ enabled: true, color: 'rgba(0,0,0,0.5)', size: 12, x: 0, y: 4 }},
        widthConstraint: {{ maximum: 190 }}
      }},
      groups: {{
        target: {{ color: {{ background: '#2b0713', border: '#ff0055', highlight: {{ background: '#ff0055', border: '#fff' }} }}, font: {{ color: '#ffffff', size: 16, bold: true }} }},
        identity: {{ color: {{ background: '#2b1f05', border: '#ffaa00' }}, font: {{ color: '#ffcc00', bold: true }} }},
        phone: {{ color: {{ background: '#052b1a', border: '#00ff88' }}, font: {{ color: '#00ff88', bold: true }} }},
        email: {{ color: {{ background: '#2b2505', border: '#ffd000' }}, font: {{ color: '#ffd000' }} }},
        platform: {{ color: {{ background: '#0c1a2b', border: '#00f0ff' }}, font: {{ color: '#7dd3fc' }} }},
        domain: {{ color: {{ background: '#0c1a2b', border: '#00f0ff' }}, font: {{ color: '#7dd3fc' }} }},
        colleague: {{ color: {{ background: '#1c0a2b', border: '#bd00ff' }}, font: {{ color: '#d8b4fe' }} }},
        breach: {{ color: {{ background: '#2b0505', border: '#ef4444' }}, font: {{ color: '#fca5a5' }} }},
        noise: {{ color: {{ background: '#0f172a', border: '#334155' }}, font: {{ color: '#64748b', size: 11 }} }},
        finding: {{ color: {{ background: '#101c2b', border: '#38bdf8' }}, font: {{ color: '#bae6fd', size: 12 }} }}
      }},
      edges: {{
        arrows: {{ to: {{ enabled: true, scaleFactor: 0.6 }} }},
        color: {{ color: '#334155', highlight: '#00f0ff', opacity: 0.9 }},
        width: 1.5,
        font: {{ color: '#64748b', size: 10, align: 'horizontal', background: '#0a0d14', strokeWidth: 0 }},
        smooth: {{ type: 'cubicBezier', forceDirection: 'vertical', roundness: 0.45 }}
      }},
      interaction: {{ hover: true, zoomView: true, dragView: true, tooltipDelay: 150 }}
    }};

    var network = new vis.Network(container, {{ nodes: nodes, edges: edges }}, options);
    network.once('afterDrawing', function() {{
      network.fit({{ animation: {{ duration: 600 }} }});
    }});
  </script>
</body>
</html>"""

