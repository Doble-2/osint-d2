"""OSINT-D2 Live Intelligence Web Server (FastAPI + WebSockets).

Features:
1. Real-time WebSocket streaming of agent thoughts and tool executions.
2. Incremental Entity Graph streaming (Vis.js compatible).
3. REST endpoints for launching targets, downloading PDF/Canvas dossiers.
4. Clean Architecture integration: Zero Node.js build steps, pure Python ASGI.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from core.config import AppSettings
from core.domain.language import Language
from core.domain.models import PersonEntity
from core.services.agent_engine import AgentEngine, AgentStep
from adapters.graph_exporter import GraphExporter
from adapters.phone_scanner import PhoneScanner
from adapters.report_exporter import export_person_html

logger = logging.getLogger(__name__)

app = FastAPI(title="OSINT-D2 Forensic Dashboard", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TEMPLATES_DIR = Path(__file__).parent / "templates"
REPORTS_DIR = Path("reports")
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


class InvestigationRequest(BaseModel):
    target: str = Field(..., description="Target username, email, phone or domain.")
    mode: str = Field(default="agent", description="'agent' for autonomous AI, 'phone' for telecom OSINT.")
    language: str = Field(default="es", description="Language code: es, en, pt, ar, ru.")


class InvestigationSession:
    def __init__(self, inv_id: str, request: InvestigationRequest):
        self.inv_id = inv_id
        self.request = request
        self.status = "running"
        self.websockets: list[WebSocket] = []
        self.person: PersonEntity | None = None
        self.pdf_path: str | None = None
        self.canvas_path: str | None = None

    async def broadcast(self, message_type: str, data: Any):
        payload = {"type": message_type, "data": data}
        dead_ws = []
        for ws in self.websockets:
            try:
                await ws.send_json(payload)
            except Exception:
                dead_ws.append(ws)
        for ws in dead_ws:
            if ws in self.websockets:
                self.websockets.remove(ws)


active_sessions: dict[str, InvestigationSession] = {}


@app.get("/", response_class=HTMLResponse)
async def get_dashboard():
    dashboard_file = TEMPLATES_DIR / "dashboard.html"
    if not dashboard_file.exists():
        raise HTTPException(status_code=404, detail="Dashboard template not found.")
    return HTMLResponse(content=dashboard_file.read_text(encoding="utf-8"))


@app.post("/api/investigate")
async def start_investigation(req: InvestigationRequest):
    inv_id = str(uuid.uuid4())[:8]
    session = InvestigationSession(inv_id, req)
    active_sessions[inv_id] = session

    asyncio.create_task(_run_investigation(session))
    return {"investigation_id": inv_id, "status": "started", "target": req.target}


@app.websocket("/ws/{inv_id}")
async def websocket_stream(websocket: WebSocket, inv_id: str):
    await websocket.accept()
    session = active_sessions.get(inv_id)
    if not session:
        await websocket.send_json({"type": "error", "data": "Investigation not found."})
        await websocket.close()
        return

    session.websockets.append(websocket)
    try:
        while True:
            # Keep alive / listen for client actions
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in session.websockets:
            session.websockets.remove(websocket)


@app.get("/api/download/{inv_id}/{file_type}")
async def download_artefact(inv_id: str, file_type: str):
    session = active_sessions.get(inv_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    safe_name = session.request.target.replace("@", "").replace("/", "_").replace("+", "")

    if file_type == "canvas":
        canvas_file = REPORTS_DIR / f"{safe_name}.canvas"
        if not canvas_file.exists():
            raise HTTPException(status_code=404, detail="Canvas not generated yet.")
        return FileResponse(canvas_file, filename=f"{safe_name}.canvas", media_type="application/json")

    if file_type == "pdf":
        pdf_file = REPORTS_DIR / "angel_calderon_dossier_vectorial.pdf"
        if not pdf_file.exists():
            pdf_file = REPORTS_DIR / f"{safe_name}.pdf"
        if pdf_file.exists():
            return FileResponse(pdf_file, filename=f"dossier_{safe_name}.pdf", media_type="application/pdf")
        raise HTTPException(status_code=404, detail="PDF not generated yet.")

    raise HTTPException(status_code=400, detail="Invalid format.")


async def _run_investigation(session: InvestigationSession):
    inv_id = session.inv_id
    target = session.request.target
    lang = Language.from_str(session.request.language)
    settings = AppSettings()

    await session.broadcast("log", f"[INIT] Objetivo inicializado: {target} (Modo: {session.request.mode.upper()})")

    # Si es teléfono directo
    if session.request.mode == "phone" or target.startswith("+") or (target.replace("-", "").isdigit() and len(target) > 7):
        await session.broadcast("log", f"[TELECOM] Escaneando número telefónico con libphonenumber...")
        phone_res = await PhoneScanner.scan(phone_number=target, settings=settings)
        await session.broadcast("phone_data", {
            "e164": phone_res.e164,
            "carrier": phone_res.carrier_name,
            "country": phone_res.country_name,
            "line_type": phone_res.line_type,
            "whatsapp": phone_res.whatsapp_active,
            "timezones": phone_res.timezones,
        })
        # Emitir nodo central del teléfono
        await session.broadcast("node_add", {
            "id": f"phone:{phone_res.e164}",
            "label": f"{phone_res.e164}\\n({phone_res.carrier_name or 'Tel'})",
            "group": "phone",
        })

    # Si es modo agente completo
    if session.request.mode == "agent":
        def on_step_callback(step: AgentStep):
            asyncio.create_task(session.broadcast("log", f"[PASO {step.step_number}] {step.tool_name} → {step.tool_args}"))
            # Si el tool fue scan_username o scan_email, emitir nodos descubiertos
            if step.tool_name == "scan_username":
                uname = step.tool_args.get("username", "")
                asyncio.create_task(session.broadcast("node_add", {
                    "id": f"user:{uname}",
                    "label": f"@{uname}",
                    "group": "social"
                }))
                asyncio.create_task(session.broadcast("edge_add", {
                    "from": f"target:{target}",
                    "to": f"user:{uname}",
                    "label": "HANDLE"
                }))

        # Nodo raíz del objetivo
        await session.broadcast("node_add", {
            "id": f"target:{target}",
            "label": f"{target}\\n[TARGET]",
            "group": "target"
        })

        engine = AgentEngine(settings=settings, enable_breach_check=False, on_step=on_step_callback)
        objective = f"Investigación exhaustiva de inteligencia del objetivo {target}."
        
        try:
            result = await engine.run(objective=objective, language=lang, max_steps=5)
            session.person = result.person

            # Exportar Canvas
            safe_name = target.replace("@", "").replace("/", "_").replace("+", "")
            graph = GraphExporter.build_graph(result.person)
            canvas_path = REPORTS_DIR / f"{safe_name}.canvas"
            GraphExporter.export_canvas(graph, canvas_path)
            session.canvas_path = str(canvas_path)

            # Transmitir grafo completo al cliente
            for n in graph.nodes:
                await session.broadcast("node_add", {"id": n.id, "label": n.label, "group": n.type.lower()})
            for e in graph.edges:
                await session.broadcast("edge_add", {"from": e.source, "to": e.target, "label": e.label or e.type})

            # Resumen final
            if result.person.analysis:
                await session.broadcast("report_done", {
                    "confidence": result.person.analysis.confidence,
                    "highlights": result.person.analysis.highlights,
                    "summary": result.person.analysis.summary,
                })
        except Exception as exc:
            await session.broadcast("log", f"[ERROR] Falló la investigación: {exc}")

    session.status = "completed"
    await session.broadcast("status", "completed")
