"""Radial Investigation Graph — multi-vector SVG map with rich data cards.

Layout logic (why it is neither a line nor plain concentric rings):
  - The SEED sits at the left; CONCLUSIONS occupy the final band on the right.
  - Each WAVE of the agent's reasoning is a vertical BAND (a "vector" of the
    investigation). Nodes discovered in parallel spread vertically inside it.
  - Edges are bezier curves with real arrow markers, colored by the discovering
    tool, so you can read "which action opened which vector".

This produces a left-to-right fan of independent research vectors instead of a
single chain, while keeping parallel discoveries visible side by side.

Each card is data-rich: type badge, correlation index, title, and up to six
labeled fields (location, followers, account age, carrier, bios...).
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Any

from core.domain.graph_models import GraphExportModel, GraphNode


# ── Paleta del grafo ──────────────────────────────────────────────────────
# Alineada con la identidad del informe PDF (esmeralda forense). Antes usaba
# neon magenta/cian, que rompía la coherencia con el resto del producto.
# (border color, fill color, short label)
_KIND = {
    "Target":    ("#34d399", "#0d3d33", "SUJETO"),      # accent-soft: el seed
    "Platform":  ("#0d9488", "#0a231d", "PERFIL"),      # accent
    "Domain":    ("#0d9488", "#0a231d", "SITIO WEB"),
    "Phone":     ("#10b981", "#062b1f", "TELÉFONO"),    # green
    "Email":     ("#f59e0b", "#2b1f05", "CORREO"),      # orange
    "Identity":  ("#34d399", "#0e2c24", "IDENTIDAD"),   # accent-soft
    "Finding":   ("#5a7d6e", "#0a231d", "CONCLUSIÓN"),  # muted
    "Colleague": ("#7a9d92", "#0e2c24", "TERCERO"),     # text-muted
    "Breach":    ("#ef4444", "#2b0707", "EXPOSICIÓN"),  # red
    "Noise":     ("#5a7d6e", "#071b16", "DESCARTADO"),  # muted, bajo contraste
}

# action -> edge colour (misma familia cromática que los nodos)
_ACTION_COLOR = {
    "scan_username": "#0d9488",
    "scan_email": "#f59e0b",
    "scan_phone": "#10b981",
    "fetch_url": "#34d399",
    "compare_avatars": "#5a7d6e",
    "correlate_stylometry": "#f59e0b",
}

# Fields drawn as "label: value" rows, in visual priority order.
_FIELD_ORDER = (
    "Plataforma", "Nombre", "Ubicación", "Antigüedad", "Cuenta creada",
    "Seguidores", "Repos", "Siguiendo", "Karma",
    "País", "Operadora", "Tipo de línea", "WhatsApp", "Zona horaria",
    "Título", "Descripción", "Web", "Twitter", "También en",
    "Sitios escaneados", "Perfiles confirmados",
    "Similitud", "Similitud avatar", "Coinciden", "Distancia dHash",
)


@dataclass
class _Card:
    node: GraphNode
    x: float
    y: float
    col: int
    width: float
    height: float
    rows: list[tuple[str, str]]


class RadialGraphRenderer:
    """Renders the investigation as a left-to-right fan of vector bands."""

    COL_WIDTH = 340.0        # horizontal step between bands
    CARD_W = 300.0
    ROW_H = 17.5
    HEADER_H = 56.0
    GAP_V = 36.0             # vertical gap between cards in a band
    MARGIN_X = 70.0
    MARGIN_Y = 150.0

    @staticmethod
    def _esc(t: Any) -> str:
        return html.escape(str(t or ""), quote=True)

    @staticmethod
    def _truncate(text: str, limit: int) -> str:
        text = re.sub(r"\s+", " ", str(text or "")).strip()
        return text if len(text) <= limit else text[: limit - 1] + "…"

    @classmethod
    def _build_rows(cls, node: GraphNode) -> list[tuple[str, str]]:
        """Selects and truncates the fields shown inside a card."""
        data = node.data or {}
        rows: list[tuple[str, str]] = []
        for key in _FIELD_ORDER:
            if key not in data:
                continue
            limit = 64 if key in ("Bio", "Descripción", "Título") else 32
            val = cls._truncate(str(data[key]), limit)
            if val:
                rows.append((key, val))
            if len(rows) >= 6:
                break

        # No structured fields -> wrap the raw evidence into readable lines
        if not rows and node.evidence:
            ev = re.sub(r"\s+", " ", node.evidence).strip()
            for chunk in [ev[i : i + 58] for i in range(0, min(len(ev), 174), 58)]:
                rows.append(("", chunk))
        return rows

    @classmethod
    def _columns(cls, chain: GraphExportModel) -> dict[str, int]:
        """Maps each node to a band index (compacted wave) with conclusions last."""
        root = chain.nodes[0].id if chain.nodes else ""
        col: dict[str, int] = {root: 0}

        raw: dict[str, int] = {}
        for e in chain.edges:
            if e.type == "CONCLUSION":
                continue
            m = re.search(r"#(\d+)", e.label or "")
            if m and e.target not in raw:
                raw[e.target] = int(m.group(1))

        distinct = sorted(set(raw.values()))
        compact = {s: i + 1 for i, s in enumerate(distinct)}
        for nid, s in raw.items():
            col[nid] = compact.get(s, 1)

        fallback = max(col.values()) if col else 1
        for n in chain.nodes:
            col.setdefault(n.id, max(1, fallback))

        if any(e.type == "CONCLUSION" for e in chain.edges):
            final = max(col.values()) + 1
            for e in chain.edges:
                if e.type == "CONCLUSION":
                    col[e.target] = final

        return col

    @classmethod
    def _layout(
        cls, chain: GraphExportModel
    ) -> tuple[list[_Card], dict[str, _Card], float, float]:
        """Places cards in vertical bands, one per investigation vector."""
        col = cls._columns(chain)

        by_col: dict[int, list[GraphNode]] = {}
        for n in chain.nodes:
            by_col.setdefault(col.get(n.id, 1), []).append(n)

        cards: list[_Card] = []
        max_bottom = 0.0

        for c in sorted(by_col.keys()):
            y = cls.MARGIN_Y
            for n in by_col[c]:
                rows = cls._build_rows(n)
                h = max(cls.HEADER_H + len(rows) * cls.ROW_H + 18, 96.0)
                x = cls.MARGIN_X + c * cls.COL_WIDTH
                cards.append(_Card(n, x, y, c, cls.CARD_W, h, rows))
                y += h + cls.GAP_V
            max_bottom = max(max_bottom, y)

        width = cls.MARGIN_X * 2 + (max(by_col.keys()) + 1) * cls.COL_WIDTH
        height = max(max_bottom + 70, 780.0)
        return cards, {c.node.id: c for c in cards}, width, height

    @classmethod
    def render_svg(
        cls,
        chain: GraphExportModel,
        *,
        target: str,
        confidence: float | None = None,
    ) -> str:
        cards, pos, width, height = cls._layout(chain)
        parts: list[str] = []

        # ── defs: glow + arrow markers + grid ────────────────────────────
        parts.append('''  <defs>
    <filter id="g" x="-40%" y="-40%" width="180%" height="180%">
      <feDropShadow dx="0" dy="0" stdDeviation="7" flood-color="#34d399" flood-opacity="0.3"/>
    </filter>''')
        for name, color in (
            ("teal", "#0d9488"), ("emerald", "#10b981"), ("amber", "#f59e0b"),
            ("sand", "#5a7d6e"), ("moss", "#7a9d92"), ("jade", "#34d399"),
            ("slate", "#5a7d6e"), ("red", "#ef4444"),
        ):
            parts.append(
                f'    <marker id="m-{name}" viewBox="0 0 10 10" refX="9" refY="5" '
                f'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
                f'<path d="M 0 1 L 10 5 L 0 9 z" fill="{color}"/></marker>'
            )
        parts.append('''    <pattern id="grid" width="44" height="44" patternUnits="userSpaceOnUse">
      <path d="M 44 0 L 0 0 0 44" fill="none" stroke="#0f1622" stroke-width="1"/>
    </pattern>
  </defs>''')

        parts.append(f'  <rect width="{width:.0f}" height="{height:.0f}" fill="#04120e"/>')
        parts.append(f'  <rect width="{width:.0f}" height="{height:.0f}" fill="url(#grid)"/>')

        # ── band guides + vector labels ──────────────────────────────────
        max_col = max((c.col for c in cards), default=0)
        n_cols = max_col + 1
        for c in range(n_cols):
            x = cls.MARGIN_X + c * cls.COL_WIDTH + cls.CARD_W / 2
            parts.append(
                f'  <line x1="{x:.0f}" y1="{cls.MARGIN_Y - 60:.0f}" x2="{x:.0f}" '
                f'y2="{height - 46:.0f}" stroke="#141d2b" stroke-width="1" stroke-dasharray="2 8"/>'
            )
            is_conclusions = c == max_col and any(
                card.col == c and card.node.type in ("Finding", "Identity") for card in cards
            )
            label = "CONCLUSIONES" if is_conclusions else f"VECTOR {c + 1}"
            parts.append(
                f'  <text x="{x:.0f}" y="{cls.MARGIN_Y - 68:.0f}" fill="#5a7d6e" font-size="10" '
                f'text-anchor="middle" letter-spacing="2.5">{label}</text>'
            )

        # ── bezier edges with arrow markers ──────────────────────────────
        for e in chain.edges:
            src, dst = pos.get(e.source), pos.get(e.target)
            if not src or not dst:
                continue
            m = re.search(r"([a-z_]{4,})", e.label or "")
            action = m.group(1) if m else ""
            if e.type == "CONCLUSION":
                action = "correlate_stylometry"
            color = _ACTION_COLOR.get(action, "#5a7d6e")
            marker = {
                "#0d9488": "m-teal", "#10b981": "m-emerald", "#f59e0b": "m-amber",
                "#5a7d6e": "m-sand", "#7a9d92": "m-moss", "#34d399": "m-jade",
            }.get(color, "m-grey")

            x1 = src.x + src.width
            y1 = src.y + src.height / 2
            x2 = dst.x - 6
            y2 = dst.y + dst.height / 2
            midx = (x1 + x2) / 2

            parts.append(
                f'  <path d="M {x1:.0f} {y1:.0f} C {midx:.0f} {y1:.0f} '
                f'{midx:.0f} {y2:.0f} {x2:.0f} {y2:.0f}" fill="none" stroke="{color}" '
                f'stroke-width="2" opacity="0.75" marker-end="url(#{marker})"/>'
            )
            if action and e.type != "CONCLUSION":
                lw = len(action) * 5.6 + 14
                ly = (y1 + y2) / 2
                parts.append(
                    f'  <rect x="{midx - lw / 2:.0f}" y="{ly - 9:.0f}" width="{lw:.0f}" height="18" '
                    f'rx="4" fill="#0b1220" stroke="{color}" stroke-width="0.8" opacity="0.95"/>'
                )
                parts.append(
                    f'  <text x="{midx:.0f}" y="{ly + 4:.0f}" fill="{color}" font-size="9.5" '
                    f'font-family="ui-monospace, monospace" text-anchor="middle">{cls._esc(action)}</text>'
                )

        # ── cards ────────────────────────────────────────────────────────
        for c in cards:
            n = c.node
            border, fill, kind = _KIND.get(n.type, ("#7a9d92", "#071b16", n.type.upper()))
            parts.append(
                f'  <rect x="{c.x:.0f}" y="{c.y:.0f}" width="{c.width:.0f}" height="{c.height:.0f}" '
                f'rx="10" fill="{fill}" stroke="{border}" stroke-width="2" filter="url(#g)"/>'
            )
            parts.append(
                f'  <rect x="{c.x:.0f}" y="{c.y:.0f}" width="{c.width:.0f}" height="30" rx="10" '
                f'fill="{border}" opacity="0.13"/>'
            )
            parts.append(
                f'  <text x="{c.x + 12:.0f}" y="{c.y + 20:.0f}" fill="{border}" font-size="9" '
                f'font-weight="bold" letter-spacing="1.3">{cls._esc(kind)}</text>'
            )
            if n.correlation is not None:
                parts.append(
                    f'  <text x="{c.x + c.width - 12:.0f}" y="{c.y + 20:.0f}" fill="#10b981" '
                    f'font-size="11" font-weight="bold" text-anchor="end">'
                    f'{int(float(n.correlation) * 100)}%</text>'
                )
            title = cls._truncate(
                re.sub(r"\[via [a-z_]+\]", "", (n.label or "").split("\n")[0]), 40
            )
            parts.append(
                f'  <text x="{c.x + 12:.0f}" y="{c.y + 47:.0f}" fill="#f8fafc" font-size="13" '
                f'font-weight="600">{cls._esc(title)}</text>'
            )
            ry = c.y + cls.HEADER_H + 12
            for label, value in c.rows:
                if label:
                    parts.append(
                        f'  <text x="{c.x + 12:.0f}" y="{ry:.0f}" fill="#7a9d92" font-size="9.5" '
                        f'font-weight="600">{cls._esc(label)}</text>'
                    )
                    parts.append(
                        f'  <text x="{c.x + 100:.0f}" y="{ry:.0f}" fill="#cbd5e1" font-size="9.5">'
                        f'{cls._esc(value)}</text>'
                    )
                else:
                    parts.append(
                        f'  <text x="{c.x + 12:.0f}" y="{ry:.0f}" fill="#a8c5bb" font-size="9.5">'
                        f'{cls._esc(value)}</text>'
                    )
                ry += cls.ROW_H

        # ── global header ────────────────────────────────────────────────
        conf_txt = f"{int(float(confidence) * 100)}%" if confidence is not None else "—"
        parts.append(
            f'  <text x="{cls.MARGIN_X:.0f}" y="52" fill="#34d399" font-size="16" font-weight="bold" '
            f'letter-spacing="1.6">GRAFO MULTI-VECTOR DE LA INVESTIGACIÓN</text>'
        )
        parts.append(
            f'  <text x="{cls.MARGIN_X:.0f}" y="78" fill="#e2e8f0" font-size="12.5">'
            f'Objetivo: {cls._esc(target)} &nbsp;·&nbsp; {n_cols} vectores &nbsp;·&nbsp; '
            f'{len(chain.nodes)} entidades &nbsp;·&nbsp; {len(chain.edges)} relaciones</text>'
        )
        parts.append(
            f'  <text x="{width - cls.MARGIN_X:.0f}" y="52" fill="#10b981" font-size="26" '
            f'font-weight="bold" text-anchor="end">{conf_txt}</text>'
        )
        parts.append(
            f'  <text x="{width - cls.MARGIN_X:.0f}" y="74" fill="#7a9d92" font-size="9.5" '
            f'text-anchor="end" letter-spacing="1.5">CONFIANZA GLOBAL</text>'
        )
        parts.append(
            f'  <line x1="{cls.MARGIN_X:.0f}" y1="96" x2="{width - cls.MARGIN_X:.0f}" y2="96" '
            f'stroke="rgba(52,211,153,0.18)" stroke-width="1"/>'
        )
        parts.append(
            f'  <text x="{cls.MARGIN_X:.0f}" y="{height - 24:.0f}" fill="#334155" font-size="10">'
            f'OSINT-D2 · cada banda vertical es un vector de investigación; cada flecha, la acción que lo abrió</text>'
        )

        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {height:.0f}" '
            f'width="{width:.0f}" height="{height:.0f}" style="background:#04120e; '
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
        """Rasterizes the graph to PNG (the SVG source stays lossless)."""
        import asyncio
        import concurrent.futures
        from pathlib import Path

        svg = cls.render_svg(chain, target=target, confidence=confidence)
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        m = re.search(r'viewBox="0 0 (\d+) (\d+)"', svg)
        vw, vh = (int(m.group(1)), int(m.group(2))) if m else (1800, 1000)

        page = (
            f'<!DOCTYPE html><html><head><meta charset="utf-8"><style>'
            f'html,body{{margin:0;padding:0;background:#04120e;overflow:hidden;}}'
            f'svg{{display:block;width:{vw}px;height:{vh}px;}}</style></head>'
            f'<body>{svg}</body></html>'
        )
        html_path = out.with_suffix(".wrap.html")
        html_path.write_text(page, encoding="utf-8")

        async def _shot() -> None:
            from playwright.async_api import async_playwright
            async with async_playwright() as p:
                b = await p.chromium.launch()
                pg = await b.new_page(
                    viewport={"width": vw, "height": vh},
                    device_scale_factor=scale,
                )
                await pg.goto(f"file://{html_path.resolve()}", wait_until="load")
                await pg.wait_for_timeout(400)
                await pg.screenshot(path=str(out), full_page=False)
                await b.close()

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
