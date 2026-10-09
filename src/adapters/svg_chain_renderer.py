"""SVG Pivot Chain Renderer — forensic flow diagram of the investigation thread.

Renders the pivot chain as a native SVG: numbered nodes as glowing boxes,
connected by marker-headed arrows that carry the action ("scan_username").
Each box shows the discovered datum and its evidence chips.

Native SVG (not HTML/JS) so it scales losslessly into the PDF, opens in any
viewer, and never depends on a browser runtime.
"""

from __future__ import annotations

import html
import re
from typing import Any

from core.domain.graph_models import GraphExportModel, GraphNode


# Paleta por tipo de hallazgo: (color borde, color relleno, etiqueta)
_KIND = {
    "Target":    ("#ff0055", "#2b0713", "PUNTO DE PARTIDA"),
    "Platform":  ("#00f0ff", "#0c1a2b", "PERFIL"),
    "Domain":    ("#00f0ff", "#0c1a2b", "SITIO WEB"),
    "Phone":     ("#00ff88", "#052b1a", "TELÉFONO"),
    "Email":     ("#ffd000", "#2b2505", "CORREO"),
    "Identity":  ("#ffaa00", "#2b1f05", "IDENTIDAD"),
    "Finding":   ("#38bdf8", "#101c2b", "CONCLUSIÓN"),
    "Colleague": ("#bd00ff", "#1c0a2b", "TERCERO"),
    "Breach":    ("#ef4444", "#2b0505", "EXPOSICIÓN"),
    "Noise":     ("#475569", "#0f172a", "DESCARTADO"),
}

_MARKER_FOR = {
    "#ff0055": "arr-red",
    "#00f0ff": "arr-cyan",
    "#00ff88": "arr-green",
    "#ffd000": "arr-yellow",
    "#ffaa00": "arr-orange",
    "#38bdf8": "arr-cyan",
    "#bd00ff": "arr-purple",
    "#ef4444": "arr-red",
    "#475569": "arr-grey",
}


class SvgChainRenderer:
    """Renders a pivot chain as a vertical forensic flow diagram in SVG."""

    BOX_W = 720
    BOX_H = 110
    GAP_Y = 78          # espacio vertical entre cajas (para la flecha)
    MARGIN_X = 60
    MARGIN_TOP = 130

    @staticmethod
    def _esc(text: str) -> str:
        return html.escape(str(text or ""), quote=True)

    @staticmethod
    def _wrap(text: str, width: int = 78) -> list[str]:
        """Word-wraps a string into lines of at most `width` characters."""
        text = re.sub(r"\s+", " ", (text or "").strip())
        if not text:
            return []
        words, lines, cur = text.split(" "), [], ""
        for w in words:
            if len(cur) + len(w) + 1 <= width:
                cur = f"{cur} {w}".strip()
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines[:3]

    @staticmethod
    def _facts(evidence: str) -> list[str]:
        """Extracts concrete data points to render as chips inside the box."""
        if not evidence:
            return []
        facts: list[str] = []
        for m in re.finditer(r"\+?\d[\d\s\-()]{7,}\d", evidence):
            val = m.group(0).strip()
            if len(re.sub(r"\D", "", val)) >= 8:
                facts.append(f"tel {val}")
        for m in re.finditer(r"[\w.+-]+@[\w-]+\.[\w.]+", evidence):
            facts.append(m.group(0))
        for key, label in (("followers", "seguidores"), ("public_repos", "repos")):
            m = re.search(rf"{key}[=:\s]+(\d+)", evidence, re.I)
            if m:
                facts.append(f"{m.group(1)} {label}")
        for m in re.finditer(
            r"([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)?,\s[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)",
            evidence,
        ):
            if len(m.group(1)) < 40:
                facts.append(m.group(1))
        if re.search(r"\bmovistar\b", evidence, re.I):
            facts.append("Movistar")
        seen: set[str] = set()
        out: list[str] = []
        for f in facts:
            if f.lower() not in seen:
                seen.add(f.lower())
                out.append(f)
        return out[:4]

    @classmethod
    def render_svg(
        cls,
        chain: GraphExportModel,
        *,
        target: str,
        confidence: float | None = None,
    ) -> str:
        """Builds the standalone SVG flow diagram."""
        nodes: list[GraphNode] = list(chain.nodes)
        n = len(nodes)
        height = cls.MARGIN_TOP + n * (cls.BOX_H + cls.GAP_Y) + 60
        width = cls.BOX_W + cls.MARGIN_X * 2 + 160
        cx = cls.MARGIN_X + cls.BOX_W / 2

        parts: list[str] = []

        # ── Defs: filtros glow + marcadores de flecha + patrón de rejilla ──
        parts.append(f'''  <defs>
    <filter id="glow" x="-30%" y="-30%" width="160%" height="160%">
      <feDropShadow dx="0" dy="0" stdDeviation="6" flood-color="#00f0ff" flood-opacity="0.35"/>
    </filter>
    <marker id="arr-cyan" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M 0 1 L 10 5 L 0 9 z" fill="#00f0ff"/>
    </marker>
    <marker id="arr-green" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M 0 1 L 10 5 L 0 9 z" fill="#00ff88"/>
    </marker>
    <marker id="arr-orange" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M 0 1 L 10 5 L 0 9 z" fill="#ffaa00"/>
    </marker>
    <marker id="arr-yellow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M 0 1 L 10 5 L 0 9 z" fill="#ffd000"/>
    </marker>
    <marker id="arr-purple" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M 0 1 L 10 5 L 0 9 z" fill="#bd00ff"/>
    </marker>
    <marker id="arr-red" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M 0 1 L 10 5 L 0 9 z" fill="#ff0055"/>
    </marker>
    <marker id="arr-grey" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M 0 1 L 10 5 L 0 9 z" fill="#475569"/>
    </marker>
    <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
      <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#111927" stroke-width="1"/>
    </pattern>
  </defs>''')

        # ── Cabecera ──
        conf_txt = f"{int(float(confidence) * 100)}%" if confidence is not None else "—"
        parts.append(f'''  <rect width="{width}" height="{height}" fill="#070a10"/>
  <rect width="{width}" height="{height}" fill="url(#grid)"/>
  <text x="{cls.MARGIN_X}" y="46" fill="#00f0ff" font-size="15" font-weight="bold" letter-spacing="1.5">HILO DE INVESTIGACIÓN — CADENA DE PIVOTES</text>
  <text x="{cls.MARGIN_X}" y="72" fill="#e2e8f0" font-size="12">Objetivo: {cls._esc(target)}  ·  {n} pasos</text>
  <text x="{width - cls.MARGIN_X}" y="46" fill="#00ff88" font-size="22" font-weight="bold" text-anchor="end">{conf_txt}</text>
  <text x="{width - cls.MARGIN_X}" y="66" fill="#64748b" font-size="9" text-anchor="end" letter-spacing="1.5">CONFIANZA GLOBAL</text>
  <line x1="{cls.MARGIN_X}" y1="92" x2="{width - cls.MARGIN_X}" y2="92" stroke="#1e293b" stroke-width="1"/>''')

        # ── Cajas + flechas ──
        for i, node in enumerate(nodes):
            y = cls.MARGIN_TOP + i * (cls.BOX_H + cls.GAP_Y)
            border, fill, kind_label = _KIND.get(node.type, ("#94a3b8", "#0f172a", node.type.upper()))
            marker = _MARKER_FOR.get(border, "arr-cyan")

            # Flecha desde la caja anterior
            if i > 0:
                prev_border = _KIND.get(nodes[i - 1].type, ("#94a3b8", "#0f172a", ""))[0]
                prev_marker = _MARKER_FOR.get(prev_border, "arr-cyan")
                ay1 = y - cls.GAP_Y + 6
                ay2 = y - 8
                parts.append(
                    f'  <line x1="{cx}" y1="{ay1}" x2="{cx}" y2="{ay2}" '
                    f'stroke="{prev_border}" stroke-width="2" marker-end="url(#{prev_marker})" opacity="0.85"/>'
                )
                # Etiqueta de la acción sobre la flecha
                action = ""
                m = re.search(r"\[via ([a-z_]+)\]", node.label or "")
                if m:
                    action = f"via {m.group(1)}"
                else:
                    action = (chain.edges[i - 1].label if i - 1 < len(chain.edges) else "") or ""
                if action:
                    lw = max(70, len(action) * 6 + 16)
                    parts.append(
                        f'  <rect x="{cx + 14}" y="{ay1 + 20}" width="{lw}" height="20" rx="5" '
                        f'fill="#0f172a" stroke="{prev_border}" stroke-width="0.8" opacity="0.95"/>'
                    )
                    parts.append(
                        f'  <text x="{cx + 14 + lw / 2}" y="{ay1 + 34}" fill="{prev_border}" '
                        f'font-size="10" font-family="ui-monospace, monospace" text-anchor="middle">{cls._esc(action)}</text>'
                    )

            # Caja del nodo
            parts.append(
                f'  <rect x="{cls.MARGIN_X}" y="{y}" width="{cls.BOX_W}" height="{cls.BOX_H}" rx="10" '
                f'fill="{fill}" stroke="{border}" stroke-width="2" filter="url(#glow)"/>'
            )
            # Índice del paso (círculo a la izquierda)
            parts.append(
                f'  <circle cx="{cls.MARGIN_X + 30}" cy="{y + 30}" r="15" fill="none" '
                f'stroke="{border}" stroke-width="1.6"/>'
            )
            parts.append(
                f'  <text x="{cls.MARGIN_X + 30}" y="{y + 35}" fill="{border}" font-size="12" '
                f'font-weight="bold" text-anchor="middle">{i}</text>'
            )
            # Etiqueta del tipo
            parts.append(
                f'  <text x="{cls.MARGIN_X + 56}" y="{y + 26}" fill="{border}" font-size="9" '
                f'font-weight="bold" letter-spacing="1.2">{cls._esc(kind_label)}</text>'
            )
            # Correlación a la derecha
            if node.correlation is not None:
                parts.append(
                    f'  <text x="{cls.MARGIN_X + cls.BOX_W - 16}" y="{y + 26}" fill="#00ff88" '
                    f'font-size="11" font-weight="bold" text-anchor="end">'
                    f'{int(float(node.correlation) * 100)}%</text>'
                )

            # Título / hallazgo (multilínea)
            title = re.sub(r"\[via [a-z_]+\]", "", (node.label or "").split("\n")[0]).strip()
            title_lines = cls._wrap(title, 74)
            ty = y + 48
            for line in title_lines:
                parts.append(
                    f'  <text x="{cls.MARGIN_X + 16}" y="{ty}" fill="#f1f5f9" font-size="12.5">{cls._esc(line)}</text>'
                )
                ty += 16

            # Chips de datos concretos
            facts = cls._facts(node.evidence or "")
            if facts:
                fx = cls.MARGIN_X + 16
                fy = y + cls.BOX_H - 18
                for fact in facts:
                    fw = len(fact) * 6.2 + 18
                    if fx + fw > cls.MARGIN_X + cls.BOX_W - 12:
                        break
                    parts.append(
                        f'  <rect x="{fx}" y="{fy - 12}" width="{fw}" height="18" rx="9" '
                        f'fill="#0f172a" stroke="#1e293b" stroke-width="1"/>'
                    )
                    parts.append(
                        f'  <text x="{fx + fw / 2}" y="{fy + 1}" fill="#93c5fd" font-size="10" '
                        f'text-anchor="middle">{cls._esc(fact)}</text>'
                    )
                    fx += fw + 8

        # ── Pie ──
        parts.append(
            f'  <text x="{cls.MARGIN_X}" y="{height - 24}" fill="#475569" font-size="10">'
            f'OSINT-D2 · Cadena de pivotes — cada flecha indica la acción que produjo el hallazgo</text>'
        )

        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
            f'width="{width}" height="{height}" style="background:#070a10; '
            f'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Roboto,sans-serif;">\n'
            + "\n".join(parts)
            + "\n</svg>"
        )

    @classmethod
    def export_png(
            cls,
            chain: GraphExportModel,
            output_path: str,
            *,
            target: str,
            confidence: float | None = None,
            scale: int = 2,
        ) -> str:
            """Renders the SVG chain to a high-resolution PNG.

            Wraps the SVG in a minimal HTML page and screenshots it: SVG scales
            losslessly, and a page (unlike a bare .svg file) screenshots reliably
            without waiting on font layout of the standalone document.
            """
            import asyncio
            import concurrent.futures
            from pathlib import Path

            svg = cls.render_svg(chain, target=target, confidence=confidence)
            out = Path(output_path)
            out.parent.mkdir(parents=True, exist_ok=True)

            # Ancho/alto reales del viewBox para encuadrar la captura
            import re as _re
            vm = _re.search(r'viewBox="0 0 (\d+) (\d+)"', svg)
            vw, vh = (int(vm.group(1)), int(vm.group(2))) if vm else (1000, 1400)

            page = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
    <style>html,body{{margin:0;padding:0;background:#070a10;}}
    svg{{display:block;width:{vw}px;height:{vh}px;}}</style></head>
    <body>{svg}</body></html>"""

            html_path = out.with_suffix(".wrap.html")
            html_path.write_text(page, encoding="utf-8")

            async def _shot() -> None:
                from playwright.async_api import async_playwright
                async with async_playwright() as p:
                    browser = await p.chromium.launch()
                    pg = await browser.new_page(
                        viewport={"width": vw, "height": vh},
                        device_scale_factor=scale,
                    )
                    await pg.goto(f"file://{html_path.resolve()}", wait_until="load")
                    await pg.wait_for_timeout(500)
                    await pg.screenshot(path=str(out), full_page=False)
                    await browser.close()

            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    pool.submit(asyncio.run, _shot()).result()
            else:
                asyncio.run(_shot())

            try:
                html_path.unlink()
            except Exception:
                pass
            return str(out)
