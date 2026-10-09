"""Graph Exporter Adapter — Analyst-grade entity correlation graph.

Design principle: SIGNAL OVER NOISE.
A useful intelligence graph shows only what advances the investigation:
  - The target and its verified identity
  - Platforms that CONFIRM the profile (with follower/repo counts)
  - High-value assets: phone, email, own domains
  - Correlated external persons, explicitly marked as excluded
Everything else (unconfirmed profiles, generic scans) is aggregated into a
single counter node instead of spawning one unreadable box per scanned site.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.domain.graph_models import GraphEdge, GraphExportModel, GraphNode
from core.domain.models import PersonEntity, SocialProfile

# Platforms worth their own node when confirmed. Anything else gets aggregated.
HIGH_SIGNAL_PLATFORMS = {
    "github", "gitlab", "bitbucket", "stackoverflow", "kaggle", "hackernews",
    "x", "twitter", "instagram", "facebook", "linkedin", "tiktok", "twitch",
    "youtube", "telegram", "reddit", "mastodon", "bluesky", "threads",
    "medium", "devto", "behance", "dribbble", "soundcloud", "pinterest",
    "keybase", "producthunt", "aboutme", "npm", "dockerhub", "pypi",
}

# Metadata keys that carry real intelligence value on a node label.
LABEL_KEYS = ("followers", "public_repos", "karma", "subscribers", "reputation")


class GraphExporter:
    """Adapts OSINT investigation results into a readable analyst graph."""

    @staticmethod
    def _platform_badge(prof: SocialProfile) -> str:
        """Builds a compact, information-dense node label for a confirmed profile."""
        meta = prof.metadata or {}
        bits: list[str] = []
        for key in LABEL_KEYS:
            value = meta.get(key)
            if value not in (None, "", 0, [], "0"):
                short = {"public_repos": "repos", "followers": "seguidores"}.get(key, key)
                bits.append(f"{value} {short}")
        platform = (prof.network_name or "").lower()
        handle = prof.username or "?"
        label = f"{platform.upper()}\n@{handle}"
        if bits:
            label += "\n" + " · ".join(bits[:2])
        return label

    @classmethod
    def build_graph(
        cls,
        person: PersonEntity,
        extra_entities: list[dict[str, Any]] | None = None,
        max_platforms: int = 12,
    ) -> GraphExportModel:
        """Constructs a high-signal graph: grouped platforms, aggregated noise."""
        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []
        seen: set[str] = set()

        def add_node(n_id: str, label: str, n_type: str, props: dict[str, Any] | None = None) -> None:
            if n_id not in seen:
                seen.add(n_id)
                nodes.append(GraphNode(id=n_id, label=label, type=n_type, properties=props or {}))

        def add_edge(src: str, dst: str, etype: str, label: str | None = None) -> None:
            if src in seen and dst in seen:
                edges.append(GraphEdge(source=src, target=dst, type=etype, label=label or etype))

        # ── 1. TARGET ROOT ────────────────────────────────────────────────
        target_id = "target:root"
        add_node(target_id, person.target, "Target", {"original_input": True})

        # ── 2. CONFIRMED PROFILES, RANKED BY INTELLIGENCE VALUE ───────────
        confirmed = [p for p in person.profiles if p.exists]
        unconfirmed_count = len([p for p in person.profiles if not p.exists])

        def signal_score(p: SocialProfile) -> int:
            meta = p.metadata or {}
            score = 3 if (p.network_name or "").lower() in HIGH_SIGNAL_PLATFORMS else 0
            score += sum(1 for k in LABEL_KEYS if meta.get(k) not in (None, "", 0, [], "0"))
            if p.bio:
                score += 1
            return score

        ranked = sorted(confirmed, key=signal_score, reverse=True)
        kept, dropped = ranked[:max_platforms], ranked[max_platforms:]

        for prof in kept:
            node_id = f"platform:{prof.network_name.lower()}"
            add_node(
                node_id,
                cls._platform_badge(prof),
                "Platform",
                {"url": prof.url, "bio": (prof.bio or "")[:160]},
            )
            add_edge(target_id, node_id, "HAS_PROFILE", "perfil confirmado")

        # ── 3. AGGREGATED NOISE (one counter node, not 50 boxes) ──────────
        noise_parts: list[str] = []
        if dropped:
            noise_parts.append(f"{len(dropped)} plataformas menores\nverificadas")
        if unconfirmed_count:
            noise_parts.append(f"{unconfirmed_count} sin perfil")
        if noise_parts:
            add_node("noise:summary", "\n".join(noise_parts), "Noise", {"collapsed": True})
            add_edge(target_id, "noise:summary", "SCANNED", "superficie explorada")

        # ── 4. CURATED HIGH-VALUE ASSETS ──────────────────────────────────
        for item in extra_entities or []:
            e_type = item.get("type", "Identity")
            raw_id = item.get("id") or f"{e_type.lower()}:{item.get('label')}"
            node_id = f"{e_type.lower()}:{str(raw_id).split(':', 1)[-1]}"
            add_node(node_id, item.get("label", node_id), e_type, item.get("properties") or {})
            source_id = item.get("source", target_id)
            if source_id not in seen:
                source_id = target_id
            add_edge(
                source_id,
                node_id,
                item.get("relation", "ASSOCIATED_WITH"),
                item.get("relation_label") or item.get("relation"),
            )

        metadata = {
            "generated_by": "OSINT-D2",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "target": person.target,
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "confirmed_profiles": len(confirmed),
            "collapsed_platforms": len(dropped) + unconfirmed_count,
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
        """Renders the entity graph as a high-resolution PNG using async Playwright.

        Note: uses the ASYNC API on purpose — this is called from within FastAPI's
        asyncio event loop, where Playwright's sync API raises a fatal error.
        """
        import asyncio
        from playwright.async_api import async_playwright

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        graph_html = graph.to_interactive_html(title=title)

        async def _render() -> None:
            async with async_playwright() as p:
                browser = await p.chromium.launch()
                page = await browser.new_page(
                    viewport={"width": width, "height": height},
                    device_scale_factor=2,
                )
                await page.set_content(graph_html, wait_until="networkidle")
                # Esperar a que la física del grafo se estabilice
                await page.wait_for_timeout(3500)
                await page.screenshot(path=str(path), full_page=False)
                await browser.close()

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # Ya estamos en un event loop: ejecutar en un hilo con su propio loop.
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(asyncio.run, _render()).result()
        else:
            asyncio.run(_render())

        return str(path)
