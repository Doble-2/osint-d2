"""Investigation Chain Builder — reconstructs the PIVOT CHAIN of an investigation.

An intelligence graph is not an inventory of findings: it is the STORY of how
each finding was reached. This module reads the agent's step trace and converts
it into a directed chain of pivots:

    @Doble-2  --[scan_username]-->  GitHub profile (bio mentions angelcalderon.dev)
              --[fetch_url]------>  Portfolio (exposes phone +58...)
              --[scan_phone]----->  Movistar / WhatsApp active
              --[correlate]------>  X @angelcaldev (84% estilo)

Each node carries: WHAT was found, HOW it was found (the tool/action) and the
concrete EVIDENCE (snippet from the tool result) that justified moving on.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from core.domain.graph_models import GraphEdge, GraphExportModel, GraphNode


@dataclass
class Pivot:
    """One link in the investigation chain."""

    order: int
    action: str                      # tool that produced the discovery
    node_id: str                     # what was discovered
    label: str                       # human-readable finding
    node_type: str                   # Target / Platform / Phone / Email / Domain / Identity / Finding
    parent_id: str                   # from where we pivoted
    evidence: str = ""               # concrete snippet justifying the pivot
    reason: str = ""                 # why the agent decided to pivot
    correlation: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)


# Resultados que NO representan un descubrimiento nuevo (metadatos internos)
_IGNORED_TOOLS = {"generate_report", "search_vector_memory"}


class ChainBuilder:
    """Builds a pivot-chain graph from an agent step trace."""

    @staticmethod
    def _extract_evidence(tool_result: str | None, max_len: int = 160) -> str:
        """Pulls a human-readable evidence snippet out of a raw tool result."""
        if not tool_result:
            return ""
        text = tool_result.strip()
        try:
            data = json.loads(text)
        except Exception:
            return text[:max_len]

        if isinstance(data, dict):
            # Bios, títulos y descripciones son la evidencia más legible
            for key in ("bio", "title", "description", "snippet", "text"):
                val = data.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip()[:max_len]
            # Métricas verificables
            bits = []
            for key in ("followers", "public_repos", "country", "carrier", "whatsapp_active", "similarity_percentage"):
                if key in data and data[key] not in (None, "", 0, False):
                    bits.append(f"{key}={data[key]}")
            if bits:
                return " · ".join(bits)[:max_len]
            # Perfiles confirmados
            profiles = data.get("profiles") or data.get("results") or []
            if isinstance(profiles, list) and profiles:
                confirmed = [p for p in profiles if isinstance(p, dict) and p.get("exists")]
                if confirmed:
                    names = ", ".join(str(p.get("network", "?")) for p in confirmed[:5])
                    return f"{len(confirmed)} perfiles confirmados: {names}"[:max_len]
            if data.get("error"):
                return f"error: {data['error']}"[:max_len]
        return text[:max_len]

    @classmethod
    def build_chain(
        cls,
        steps: list[Any],
        target: str,
        person: Any | None = None,
    ) -> GraphExportModel:
        """Converts an agent step trace into a pivot-chain GraphExportModel."""
        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []
        seen: set[str] = set()

        def add_node(n_id: str, label: str, n_type: Any, **kwargs: Any) -> None:
            if n_id not in seen:
                seen.add(n_id)
                nodes.append(GraphNode(id=n_id, label=label, type=n_type, **kwargs))

        # ── Raíz: el punto de partida de la investigación ─────────────────
        root_id = "seed:target"
        add_node(root_id, f"PUNTO DE PARTIDA\n{target}", "Target", evidence=f"Objetivo declarado: {target}")

        last_id = root_id
        order = 0
        # Rastrear el último nodo creado por tipo para enlazar pivotes coherentemente
        last_by_kind: dict[str, str] = {}

        for step in steps:
            tool = getattr(step, "tool_name", None)
            args = getattr(step, "tool_args", None) or {}
            result = getattr(step, "tool_result", None)
            if not tool or tool in _IGNORED_TOOLS:
                continue

            order += 1
            evidence = cls._extract_evidence(result)

            # ── scan_username → nodo de handle/pivote ────────────────────
            if tool == "scan_username":
                username = str(args.get("username", "")).strip()
                if not username:
                    continue
                nid = f"pivot:handle:{username.lower()}"
                add_node(
                    nid,
                    f"@{username}\n[via scan_username]",
                    "Platform",
                    evidence=evidence or f"Escaneo de usernames para '{username}'",
                    correlation=None,
                )
                edges.append(GraphEdge(
                    source=last_id, target=nid, type="PIVOT",
                    label=f"#{order} scan_username", properties={"action": tool},
                ))
                last_id = nid
                last_by_kind["handle"] = nid

            # ── scan_email ───────────────────────────────────────────────
            elif tool == "scan_email":
                email = str(args.get("email", "")).strip()
                if not email:
                    continue
                nid = f"pivot:email:{email.lower()}"
                add_node(nid, f"{email}\n[via scan_email]", "Email", evidence=evidence)
                edges.append(GraphEdge(
                    source=last_id, target=nid, type="PIVOT",
                    label=f"#{order} scan_email", properties={"action": tool},
                ))
                last_id = nid

            # ── scan_phone ───────────────────────────────────────────────
            elif tool == "scan_phone":
                phone = str(args.get("phone_number", "")).strip()
                if not phone:
                    continue
                nid = f"pivot:phone:{re.sub(r'[^0-9+]', '', phone)}"
                add_node(nid, f"{phone}\n[via scan_phone]", "Phone", evidence=evidence)
                edges.append(GraphEdge(
                    source=last_id, target=nid, type="PIVOT",
                    label=f"#{order} scan_phone", properties={"action": tool},
                ))
                last_id = nid

            # ── fetch_url → el pivote más importante ─────────────────────
            elif tool == "fetch_url":
                url = str(args.get("url", "")).strip()
                if not url:
                    continue
                domain = re.sub(r"^https?://(www\.)?", "", url).split("/")[0]
                nid = f"pivot:url:{domain}"
                add_node(
                    nid,
                    f"{domain}\n[via fetch_url]",
                    "Domain",
                    evidence=evidence or f"Contenido extraído de {url}",
                    properties={"url": url},
                )
                edges.append(GraphEdge(
                    source=last_id, target=nid, type="PIVOT",
                    label=f"#{order} fetch_url", properties={"action": tool, "url": url},
                ))
                last_id = nid

            # ── correlate_stylometry → conclusión de autoría ─────────────
            elif tool == "correlate_stylometry":
                sample = str(args.get("sample_text", "")).strip()
                nid = f"pivot:style:{order}"
                # Extraer score si está en el resultado
                score = None
                if result:
                    m = re.search(r"(0\.\d+|1\.0)", str(result))
                    if m:
                        try:
                            score = float(m.group(1))
                        except Exception:
                            score = None
                label = "CORRELACIÓN ESTILOMÉTRICA"
                if score is not None:
                    label += f"\n{int(score * 100)}% misma autoría"
                add_node(
                    nid, label, "Finding",
                    evidence=(evidence or sample[:120]),
                    correlation=score,
                )
                edges.append(GraphEdge(
                    source=last_id, target=nid, type="PIVOT",
                    label=f"#{order} correlate_stylometry",
                    properties={"action": tool},
                ))
                last_id = nid

            # ── compare_avatars → conclusión de identidad visual ─────────
            elif tool == "compare_avatars":
                nid = f"pivot:avatar:{order}"
                add_node(nid, "COMPARACIÓN DE AVATARES\n(dHash)", "Finding", evidence=evidence)
                edges.append(GraphEdge(
                    source=last_id, target=nid, type="PIVOT",
                    label=f"#{order} compare_avatars", properties={"action": tool},
                ))
                last_id = nid

        # ── Conclusiones finales del análisis (cierre del hilo) ───────────
        analysis = getattr(person, "analysis", None) if person else None
        if analysis:
            confidence = getattr(analysis, "confidence", None)
            for idx, h in enumerate(list(getattr(analysis, "highlights", []) or [])[:5]):
                text = str(h).strip()
                if not text:
                    continue
                nid = f"conclusion:{idx}"
                label = text if len(text) <= 80 else text[:77] + "..."
                add_node(
                    nid, label, "Finding",
                    evidence=text,
                    correlation=float(confidence) if confidence is not None else None,
                )
                edges.append(GraphEdge(
                    source=last_id, target=nid, type="CONCLUSION",
                    label="conclusión", properties={"full_text": text},
                ))

            if confidence is not None:
                cid = "conclusion:confidence"
                add_node(
                    cid,
                    f"CONFIANZA GLOBAL\n{int(float(confidence) * 100)}%",
                    "Identity",
                    evidence=f"{len(getattr(analysis, 'highlights', []) or [])} conclusiones correlacionadas",
                    correlation=float(confidence),
                )
                edges.append(GraphEdge(source=last_id, target=cid, type="CONCLUSION", label="cierre"))

        metadata = {
            "mode": "pivot_chain",
            "target": target,
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "pivots": order,
        }
        return GraphExportModel(nodes=nodes, edges=edges, metadata=metadata)
