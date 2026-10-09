"""Investigation Timeline Renderer — a readable, top-to-bottom investigation thread.

Why this exists:
A network graph with 20+ nodes is unreadable for the actual question an analyst
asks: "how did I get from this username to that conclusion?". This renders the
pivot chain as a vertical timeline — one numbered step per discovery, with the
CONCRETE data each step produced (name, location, phone, email, age...) shown
inline, plus the raw evidence underneath.

Output is a standalone HTML (dark theme, no external deps beyond a font) that
also screenshots cleanly into the dossier PDF.
"""

from __future__ import annotations

import html
import re
from typing import Any

from core.domain.graph_models import GraphExportModel, GraphNode


# Cada tipo de hallazgo tiene un color y una etiqueta corta.
_KIND_STYLE = {
    "Target": ("#ff0055", "PUNTO DE PARTIDA"),
    "Platform": ("#00f0ff", "PERFIL"),
    "Domain": ("#00f0ff", "SITIO WEB"),
    "Phone": ("#00ff88", "TELÉFONO"),
    "Email": ("#ffd000", "CORREO"),
    "Identity": ("#ffaa00", "IDENTIDAD"),
    "Finding": ("#38bdf8", "CONCLUSIÓN"),
    "Colleague": ("#bd00ff", "TERCERO"),
    "Breach": ("#ef4444", "EXPOSICIÓN"),
    "Noise": ("#475569", "DESCARTADO"),
}


class TimelineRenderer:
    """Renders a pivot chain as a vertical investigation timeline."""

    @staticmethod
    def _clean(text: str) -> str:
        """Strips tool markers and normalizes whitespace for display."""
        if not text:
            return ""
        t = re.sub(r"\[(via|#)\s*[^\]]*\]", "", text)
        t = re.sub(r"\s+", " ", t).strip()
        return t

    @classmethod
    def render_html(
        cls,
        chain: GraphExportModel,
        *,
        target: str,
        confidence: float | None = None,
    ) -> str:
        """Builds the standalone timeline HTML."""
        # Ordenar los nodos por el orden de los pivotes (los ids llevan el orden
        # cuando aplica; si no, se respeta el orden de inserción).
        ordered: list[GraphNode] = list(chain.nodes)

        steps_html: list[str] = []
        for idx, node in enumerate(ordered):
            color, kind_label = _KIND_STYLE.get(node.type, ("#94a3b8", node.type.upper()))
            title = cls._clean(node.label.splitlines()[0]) if node.label else node.id
            full_title = cls._clean(node.label)
            evidence = (node.evidence or "").strip()
            corr = ""
            if node.correlation is not None:
                corr = f'<span class="corr">{int(float(node.correlation) * 100)}%</span>'

            # Detectar datos concretos dentro de la evidencia para destacarlos
            facts = cls._extract_facts(evidence)
            facts_html = ""
            if facts:
                chips = "".join(f'<span class="chip">{html.escape(f)}</span>' for f in facts)
                facts_html = f'<div class="facts">{chips}</div>'

            # El nombre de la acción (de qué herramienta salió) viene en el label
            action = ""
            m = re.search(r"\[via ([a-z_]+)\]", node.label or "")
            if m:
                action = f'<span class="action">via {html.escape(m.group(1))}</span>'

            steps_html.append(f'''
      <div class="step">
        <div class="rail">
          <div class="dot" style="border-color:{color};background:{color}22"></div>
          <div class="line"></div>
        </div>
        <div class="body">
          <div class="head">
            <span class="kind" style="color:{color};border-color:{color}55">{kind_label}</span>
            <span class="order">#{idx}</span>
            {action}
            {corr}
          </div>
          <div class="title">{html.escape(full_title)}</div>
          {facts_html}
          {f'<div class="evidence">{html.escape(evidence[:300])}</div>' if evidence and not facts else ''}
        </div>
      </div>''')

        conf_html = ""
        if confidence is not None:
            conf_html = f'''
    <div class="conf">
      <div class="conf-label">CONFIANZA GLOBAL</div>
      <div class="conf-value">{int(float(confidence) * 100)}%</div>
    </div>'''

        return f'''<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Hilo de investigación — {html.escape(target)}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: #070a10; color: #e2e8f0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; padding: 28px 24px 40px; }}
  .header {{ display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 1px solid #1e293b; padding-bottom: 16px; margin-bottom: 26px; gap: 20px; }}
  .header h1 {{ font-size: 17px; color: #ffffff; letter-spacing: 0.3px; }}
  .header p {{ font-size: 11px; color: #64748b; margin-top: 5px; line-height: 1.5; }}
  .conf {{ text-align: right; flex-shrink: 0; }}
  .conf-label {{ font-size: 9px; color: #64748b; letter-spacing: 1.5px; }}
  .conf-value {{ font-size: 26px; color: #00ff88; font-weight: 700; line-height: 1.1; }}

  .step {{ display: flex; gap: 16px; }}
  .rail {{ width: 18px; display: flex; flex-direction: column; align-items: center; flex-shrink: 0; }}
  .dot {{ width: 13px; height: 13px; border-radius: 50%; border: 2.5px solid; margin-top: 18px; flex-shrink: 0; }}
  .line {{ width: 2px; flex: 1; background: linear-gradient(#1e293b, #0f172a); min-height: 14px; }}
  .step:last-child .line {{ background: transparent; }}

  .body {{ flex: 1; padding: 14px 0 18px; }}
  .head {{ display: flex; align-items: center; gap: 9px; flex-wrap: wrap; margin-bottom: 7px; }}
  .kind {{ font-size: 9px; font-weight: 800; letter-spacing: 1.2px; padding: 2.5px 7px; border: 1px solid; border-radius: 4px; }}
  .order {{ font-size: 10px; color: #475569; font-family: ui-monospace, monospace; }}
  .action {{ font-size: 9px; color: #64748b; font-family: ui-monospace, monospace; background: #0f172a; padding: 2.5px 7px; border-radius: 4px; }}
  .corr {{ font-size: 10px; font-weight: 700; color: #00ff88; margin-left: auto; }}

  .title {{ font-size: 14px; color: #f1f5f9; line-height: 1.45; font-weight: 500; }}
  .facts {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: 9px; }}
  .chip {{ font-size: 11px; background: #0f172a; border: 1px solid #1e293b; color: #93c5fd; padding: 3.5px 9px; border-radius: 12px; }}
  .evidence {{ font-size: 11px; color: #64748b; margin-top: 8px; line-height: 1.55; font-family: ui-monospace, monospace; border-left: 2px solid #1e293b; padding-left: 10px; }}
</style>
</head>
<body>
  <div class="header">
    <div>
      <h1>Hilo de investigación — {html.escape(target)}</h1>
      <p>Secuencia de pivotes: cada paso indica qué se descubrió, con qué acción y la evidencia que lo sustenta.</p>
    </div>
    {conf_html}
  </div>
  {''.join(steps_html)}
</body>
</html>'''

    @staticmethod
    def _extract_facts(evidence: str) -> list[str]:
        """Pulls concrete data points (phone, email, location, counts) out of evidence text."""
        if not evidence:
            return []
        facts: list[str] = []
        # Teléfono internacional
        for m in re.finditer(r"\+?\d[\d\s\-()]{7,}\d", evidence):
            val = m.group(0).strip()
            if len(re.sub(r"\D", "", val)) >= 8:
                facts.append(f"tel {val}")
        # Email
        for m in re.finditer(r"[\w.+-]+@[\w-]+\.[\w.]+", evidence):
            facts.append(m.group(0))
        # Métricas de perfil
        for key, label in (("followers", "seguidores"), ("public_repos", "repos"), ("karma", "karma")):
            m = re.search(rf"{key}[=:\s]+(\d+)", evidence, re.I)
            if m:
                facts.append(f"{m.group(1)} {label}")
        # Ubicación declarada en bios ("City, Country")
        for m in re.finditer(r"([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)?,\s[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)", evidence):
            cand = m.group(1)
            if cand not in facts and len(cand) < 40:
                facts.append(cand)
        # Carrier / whatsapp
        m = re.search(r"(movistar|digitel|movilnet|whatsapp[=:\s]+true)", evidence, re.I)
        if m:
            facts.append(m.group(1).lower())
        # Deduplicar preservando orden
        seen = set()
        out = []
        for f in facts:
            if f.lower() not in seen:
                seen.add(f.lower())
                out.append(f)
        return out[:5]
