"""Investigation Chain Builder — reconstructs the PIVOT CHAIN of an investigation.

An intelligence graph is not an inventory of findings: it is the STORY of how
each finding was reached. This module reads the agent's step trace and converts
it into a directed chain of pivots:

    @johndoe  --[scan_username]-->  GitHub profile (bio mentions johndoe.dev)
              --[fetch_url]------>  Portfolio (exposes phone +1...)
              --[scan_phone]----->  AT&T / WhatsApp active
              --[correlate]------>  X @jdoe_dev (84% style match)

Each node carries: WHAT was found, HOW it was found (the tool/action) and the
concrete EVIDENCE (snippet from the tool result) that justified moving on.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from adapters.i18n import load_translations
from core.domain.graph_models import GraphEdge, GraphExportModel, GraphNode
from core.domain.language import Language


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


    # Campos de perfil con valor de inteligencia. La etiqueta es un id estable:
    # el renderer la traduce al idioma de la investigación.
    _PROFILE_FIELDS = (
        ("name", "name"),
        ("location", "location"),
        ("bio", "bio"),
        ("blog", "website"),
        ("followers", "followers"),
        ("following", "following"),
        ("public_repos", "repos"),
        ("twitter_username", "twitter"),
        ("created_at", "account_created"),
        ("karma", "karma"),
        ("subscribers", "subscribers"),
    )

    @classmethod
    def _extract_data(cls, tool_result: str | None, tool: str, strings: dict[str, str]) -> dict[str, str]:
        """Pulls every intelligence-bearing field out of a raw tool result.

        Profiles carry far more than a bio: location, follower counts, account
        age, linked accounts. The earlier version surfaced only one snippet,
        which is why each box felt empty.
        """
        data: dict[str, str] = {}
        if not tool_result:
            return data
        try:
            payload = json.loads(tool_result)
        except Exception:
            return data

        if not isinstance(payload, dict):
            return data

        # ── Teléfono: datos de telecom ───────────────────────────────────
        if tool == "scan_phone" or "carrier" in payload:
            for key, label in (
                ("country", "country"), ("carrier", "carrier"), ("line_type", "line_type"),
                ("timezones", "timezone"), ("whatsapp_active", "whatsapp"),
            ):
                val = payload.get(key)
                if val not in (None, "", [], False):
                    data[label] = strings["yes"] if val is True else str(val)
            if payload.get("associated_names"):
                data["associated_names"] = ", ".join(str(x) for x in payload["associated_names"][:3])

        # ── Email: cuentas descubiertas + brechas ────────────────────────
        if tool == "scan_email" or "total_scanned" in payload:
            confirmed = payload.get("confirmed")
            total = payload.get("total_scanned")
            if total:
                data["sites_scanned"] = str(total)
            if confirmed:
                data["confirmed_profiles"] = str(confirmed)

        # ── Estilometría ─────────────────────────────────────────────────
        # El score se traduce a una etiqueta legible: un numero crudo (0.51) no
        # le dice nada al analista. Los umbrales coinciden con los que el
        # prompt del agente declara para que ambos hablen el mismo idioma.
        if tool == "correlate_stylometry":
            if payload.get("similarity_percentage") is not None:
                data["similarity"] = f"{payload['similarity_percentage']}%"
            score = payload.get("stylometric_score")
            if score is not None:
                try:
                    value = float(score)
                except (TypeError, ValueError):
                    data["stylometric_score"] = str(score)
                else:
                    if value >= 0.70:
                        label = strings["style_same"]
                    elif value >= 0.40:
                        label = strings["style_moderate"]
                    else:
                        label = strings["style_unrelated"]
                    data["stylometric_score"] = f"{value:.2f} — {label}"
            if payload.get("hamming_distance") is not None:
                data["distance"] = str(payload["hamming_distance"])

        # ── Comparación de avatares ──────────────────────────────────────
        if tool == "compare_avatars":
            if payload.get("similarity_percentage") is not None:
                data["avatar_similarity"] = f"{payload['similarity_percentage']}%"
            if payload.get("matched") is not None:
                data["match"] = strings["yes"] if payload["matched"] else strings["no"]
            if payload.get("hamming_distance") is not None:
                data["dhash_distance"] = str(payload["hamming_distance"])

        # ── Perfiles: el caso más rico ───────────────────────────────────
        profiles = payload.get("profiles") or payload.get("results") or []
        if isinstance(profiles, list) and profiles:
            # Tomar el perfil CONFIRMADO con más campos disponibles
            best: dict[str, Any] = {}
            best_fields = -1
            for p in profiles:
                if not isinstance(p, dict) or not p.get("exists"):
                    continue
                fields = sum(1 for key, _ in cls._PROFILE_FIELDS if p.get(key) not in (None, "", [], 0))
                if fields > best_fields:
                    best, best_fields = p, fields
            if best:
                data["platform"] = str(best.get("network", "?"))
                for key, label in cls._PROFILE_FIELDS:
                    val = best.get(key)
                    if val in (None, "", [], 0):
                        continue
                    if key in ("followers", "following", "public_repos", "karma", "subscribers"):
                        data[label] = str(val)
                    elif key == "bio":
                        data[label] = str(val)[:110]
                    else:
                        data[label] = str(val)[:70]
                confirmed_count = len([p for p in profiles if isinstance(p, dict) and p.get("exists")])
                if confirmed_count > 1:
                    others = [
                        str(p.get("network")) for p in profiles
                        if isinstance(p, dict) and p.get("exists") and p.get("network") != best.get("network")
                    ][:6]
                    if others:
                        data["also_on"] = ", ".join(others)

        # ── fetch_url: contenido de la página ────────────────────────────
        if tool == "fetch_url" or "status_code" in payload:
            if payload.get("title"):
                data["title"] = str(payload["title"])[:80]
            if payload.get("description"):
                data["description"] = str(payload["description"])[:110]
            if payload.get("url"):
                data["url"] = str(payload["url"])[:70]
            if payload.get("emails"):
                data["emails_on_page"] = ", ".join(str(x) for x in payload["emails"][:3])
            if payload.get("phones"):
                data["phones_on_page"] = ", ".join(str(x) for x in payload["phones"][:3])

        return {k: v for k, v in data.items() if v not in (None, "", "None")}

    @staticmethod
    def _extract_evidence(tool_result: str | None, strings: dict[str, str], max_len: int = 160) -> str:
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
                    return strings["n_confirmed"].format(n=len(confirmed), names=names)[:max_len]
            if data.get("error"):
                return f"error: {data['error']}"[:max_len]
        return text[:max_len]

    @classmethod
    def build_chain(
        cls,
        steps: list[Any],
        target: str,
        person: Any | None = None,
        language: Language = Language.ENGLISH,
    ) -> GraphExportModel:
        """Converts an agent step trace into a pivot-chain GraphExportModel."""
        strings: dict[str, str] = load_translations(language.value)["graph"]
        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []
        seen: set[str] = set()

        def add_node(n_id: str, label: str, n_type: Any, **kwargs: Any) -> None:
            if n_id not in seen:
                seen.add(n_id)
                nodes.append(GraphNode(id=n_id, label=label, type=n_type, **kwargs))

        # Índice de perfiles confirmados por usuario, para enriquecer los nodos
        # con la metadata completa (ubicación, seguidores, antigüedad...).
        profiles_by_user: dict[str, Any] = {}
        if person is not None:
            for prof in getattr(person, "profiles", []) or []:
                if not getattr(prof, "exists", False):
                    continue
                key = str(getattr(prof, "username", "")).lower().lstrip("@")
                if key:
                    profiles_by_user.setdefault(key, prof)

        def enrich_with_profile(data: dict[str, str], username: str) -> dict[str, str]:
            """Adds every available field from the matched confirmed profile."""
            prof = profiles_by_user.get(username.lower().lstrip("@"))
            if not prof:
                return data
            md = getattr(prof, "metadata", None) or {}
            out = dict(data)
            out.setdefault("platform", str(getattr(prof, "network_name", "?")))
            for key, label in cls._PROFILE_FIELDS:
                val = md.get(key)
                if val in (None, "", [], 0) or label in out:
                    continue
                if key in ("followers", "following", "public_repos", "karma", "subscribers"):
                    out[label] = str(val)
                elif key == "bio":
                    out[label] = str(val)[:150]
                else:
                    out[label] = str(val)[:70]
            # Antigüedad de la cuenta en años
            created = md.get("created_at")
            if created and "account_created" not in out:
                out["account_created"] = str(created)[:10]
                try:
                    from datetime import datetime, timezone
                    dt = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
                    years = (datetime.now(timezone.utc) - dt).days / 365.25
                    out["account_age"] = strings["years"].format(n=f"{years:.1f}")
                except Exception:
                    pass
            return out

        # ── Raíz: el punto de partida de la investigación ─────────────────
        root_id = "seed:target"
        add_node(root_id, f"{target}", "Target",
                 evidence=strings["declared_target"].format(target=target),
                 data={"seed": target, "seed_type": strings["declared_target_type"]})

        last_id = root_id
        order = 0
        # Rastrear el último nodo creado por tipo para enlazar pivotes coherentemente
        last_by_kind: dict[str, str] = {}
        # Padre por oleada: los nodos descubiertos en el MISMO step_number son
        # hermanos (vectores paralelos), no una cadena. Se cuelgan del nodo que
        # estaba activo al iniciar esa oleada.
        wave_parent: dict[int, str] = {}
        current_wave = 0
        wave_root = root_id

        for step in steps:
            tool = getattr(step, "tool_name", None)
            args = getattr(step, "tool_args", None) or {}
            result = getattr(step, "tool_result", None)
            if not tool or tool in _IGNORED_TOOLS:
                continue

            order += 1
            step_num = int(getattr(step, "step_number", order) or order)
            # Nueva oleada: los nodos de este step cuelgan del que estaba activo
            # al abrir la oleada (ramificación), no del hermano anterior.
            if step_num != current_wave:
                current_wave = step_num
                wave_root = last_id
                wave_parent[step_num] = wave_root
            parent_id = wave_parent.get(step_num, root_id)
            evidence = cls._extract_evidence(result, strings)
            step_data = cls._extract_data(result, tool, strings)

            # ── scan_username → nodo de handle/pivote ────────────────────
            if tool == "scan_username":
                username = str(args.get("username", "")).strip()
                if not username:
                    continue
                nid = f"pivot:handle:{username.lower()}"
                add_node(
                    nid,
                    f"@{username}",
                    "Platform",
                    evidence=evidence or strings["username_scan"].format(username=username),
                    correlation=None,
                    data=enrich_with_profile(step_data, username),
                )
                edges.append(GraphEdge(
                    source=parent_id, target=nid, type="PIVOT",
                    label=f"#{step_num} scan_username", properties={"action": tool},
                ))
                last_id = nid
                last_by_kind["handle"] = nid

            # ── scan_email ───────────────────────────────────────────────
            elif tool == "scan_email":
                email = str(args.get("email", "")).strip()
                if not email:
                    continue
                nid = f"pivot:email:{email.lower()}"
                add_node(nid, f"{email}", "Email", evidence=evidence, data=step_data)
                edges.append(GraphEdge(
                    source=parent_id, target=nid, type="PIVOT",
                    label=f"#{step_num} scan_email", properties={"action": tool},
                ))
                last_id = nid

            # ── scan_phone ───────────────────────────────────────────────
            elif tool == "scan_phone":
                phone = str(args.get("phone_number", "")).strip()
                if not phone:
                    continue
                nid = f"pivot:phone:{re.sub(r'[^0-9+]', '', phone)}"
                add_node(nid, f"{phone}", "Phone", evidence=evidence, data=step_data)
                edges.append(GraphEdge(
                    source=parent_id, target=nid, type="PIVOT",
                    label=f"#{step_num} scan_phone", properties={"action": tool},
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
                    f"{domain}",
                    "Domain",
                    evidence=evidence or strings["content_from"].format(url=url),
                    properties={"url": url},
                    data=step_data,
                )
                edges.append(GraphEdge(
                    source=parent_id, target=nid, type="PIVOT",
                    label=f"#{step_num} fetch_url", properties={"action": tool, "url": url},
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
                label = strings["stylometry_title"]
                if score is not None:
                    label += "\n" + strings["same_author"].format(n=int(score * 100))
                add_node(
                    nid, label, "Finding",
                    evidence=(evidence or sample[:120]),
                    correlation=score,
                    data=step_data,
                )
                edges.append(GraphEdge(
                    source=parent_id, target=nid, type="PIVOT",
                    label=f"#{step_num} correlate_stylometry",
                    properties={"action": tool},
                ))
                last_id = nid

            # ── compare_avatars → conclusión de identidad visual ─────────
            elif tool == "compare_avatars":
                nid = f"pivot:avatar:{order}"
                add_node(nid, strings["avatar_title"], "Finding",
                             evidence=evidence, data=step_data)
                edges.append(GraphEdge(
                    source=parent_id, target=nid, type="PIVOT",
                    label=f"#{step_num} compare_avatars", properties={"action": tool},
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
                    label="conclusion", properties={"full_text": text},
                ))

            if confidence is not None:
                cid = "conclusion:confidence"
                add_node(
                    cid,
                    f"{strings['global_confidence']}\n{int(float(confidence) * 100)}%",
                    "Identity",
                    evidence=strings["n_conclusions"].format(n=len(getattr(analysis, "highlights", []) or [])),
                    correlation=float(confidence),
                )
                edges.append(GraphEdge(source=last_id, target=cid, type="CONCLUSION", label="closing"))

        metadata = {
            "mode": "pivot_chain",
            "target": target,
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "pivots": order,
        }
        return GraphExportModel(nodes=nodes, edges=edges, metadata=metadata)
