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
    target: str = Field(..., description="Target name or primary identifier.")
    usernames: list[str] = Field(default_factory=list, description="List of usernames/handles to investigate.")
    emails: list[str] = Field(default_factory=list, description="List of email addresses.")
    phones: list[str] = Field(default_factory=list, description="List of phone numbers.")
    trust_anchors: list[str] = Field(default_factory=list, description="Verified trust anchors (e.g. github:Doble-2).")
    mode: str = Field(default="agent", description="'agent' for autonomous AI, 'hunt' for full OSINT sweep, 'phone' for telecom.")
    ai_provider: str = Field(default="deepseek", description="AI provider: deepseek, ollama, openai.")
    language: str = Field(default="es", description="Language code: es, en, pt, ar, ru.")
    max_steps: int = Field(default=6, description="Max agent reasoning steps.")
    enable_breach_check: bool = Field(default=False, description="Check data breaches.")


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

    safe_name = session.request.target.replace("@", "").replace("/", "_").replace("+", "").replace(" ", "_")

    if file_type == "canvas":
        canvas_file = REPORTS_DIR / f"{safe_name}.canvas"
        if not canvas_file.exists():
            # Buscar cualquier canvas generado para esta sesión
            if session.canvas_path and Path(session.canvas_path).exists():
                canvas_file = Path(session.canvas_path)
            else:
                raise HTTPException(status_code=404, detail="Canvas not generated yet.")
        return FileResponse(canvas_file, filename=f"{safe_name}.canvas", media_type="application/json")

    if file_type == "pdf":
        pdf_file = REPORTS_DIR / f"{safe_name}_dossier.pdf"
        if not pdf_file.exists():
            if session.pdf_path and Path(session.pdf_path).exists():
                pdf_file = Path(session.pdf_path)
            else:
                raise HTTPException(status_code=404, detail="PDF not generated yet.")
        return FileResponse(pdf_file, filename=f"dossier_{safe_name}.pdf", media_type="application/pdf")

    raise HTTPException(status_code=400, detail="Invalid format.")


async def _run_investigation(session: InvestigationSession):
    inv_id = session.inv_id
    req = session.request
    target = req.target
    lang = Language.from_str(req.language)
    settings = AppSettings()

    if req.ai_provider:
        settings.ai_provider = req.ai_provider
        if req.ai_provider == "ollama":
            settings.ai_base_url = "http://localhost:11434/v1"
            settings.ai_model = "qwen2.5-coder:7b"

    await session.broadcast("log", f"[INIT] Objetivo inicializado: {target} (Modo: {req.mode.upper()})")

    # Si hay teléfonos especificados
    for phone_num in req.phones:
        await session.broadcast("log", f"[TELECOM] Escaneando teléfono {phone_num}...")
        phone_res = await PhoneScanner.scan(phone_number=phone_num, settings=settings)
        await session.broadcast("phone_data", {
            "e164": phone_res.e164,
            "carrier": phone_res.carrier_name,
            "country": phone_res.country_name,
            "line_type": phone_res.line_type,
            "whatsapp": phone_res.whatsapp_active,
            "timezones": phone_res.timezones,
        })
        await session.broadcast("node_add", {
            "id": f"phone:{phone_res.e164}",
            "label": f"{phone_res.e164}\\n({phone_res.carrier_name or 'Tel'})",
            "group": "phone",
        })
        await session.broadcast("edge_add", {
            "from": f"target:{target}",
            "to": f"phone:{phone_res.e164}",
            "label": "PHONE_NUM",
        })

    # Si hay emails especificados
    for email in req.emails:
        await session.broadcast("node_add", {
            "id": f"email:{email}",
            "label": f"{email}",
            "group": "email",
        })
        await session.broadcast("edge_add", {
            "from": f"target:{target}",
            "to": f"email:{email}",
            "label": "USES_EMAIL",
        })

    # Si hay anclas de confianza
    for anchor in req.trust_anchors:
        await session.broadcast("log", f"[TRUST ANCHOR] Ancla verificada fijada: {anchor}")
        await session.broadcast("node_add", {
            "id": f"anchor:{anchor}",
            "label": f"[VERIFIED]\\n{anchor}",
            "group": "identity",
        })
        await session.broadcast("edge_add", {
            "from": f"target:{target}",
            "to": f"anchor:{anchor}",
            "label": "TRUST_ANCHOR",
        })

    # Modo Agente Autónomo
    if req.mode == "agent":
        def on_step_callback(step: AgentStep):
            asyncio.create_task(session.broadcast("log", f"[PASO {step.step_number}] {step.tool_name} → {step.tool_args}"))
            if step.tool_name == "scan_username":
                uname = step.tool_args.get("username", "")
                asyncio.create_task(session.broadcast("node_add", {"id": f"user:{uname}", "label": f"@{uname}", "group": "social"}))
                asyncio.create_task(session.broadcast("edge_add", {"from": f"target:{target}", "to": f"user:{uname}", "label": "HANDLE"}))
            elif step.tool_name == "scan_email":
                em = step.tool_args.get("email", "")
                asyncio.create_task(session.broadcast("node_add", {"id": f"email:{em}", "label": em, "group": "email"}))
                asyncio.create_task(session.broadcast("edge_add", {"from": f"target:{target}", "to": f"email:{em}", "label": "EMAIL"}))
            elif step.tool_name == "scan_phone":
                ph = step.tool_args.get("phone_number", "")
                asyncio.create_task(session.broadcast("node_add", {"id": f"phone:{ph}", "label": ph, "group": "phone"}))
                asyncio.create_task(session.broadcast("edge_add", {"from": f"target:{target}", "to": f"phone:{ph}", "label": "PHONE"}))

        await session.broadcast("node_add", {
            "id": f"target:{target}",
            "label": f"{target}\\n[TARGET]",
            "group": "target"
        })

        engine = AgentEngine(settings=settings, enable_breach_check=req.enable_breach_check, on_step=on_step_callback)
        
        # Armar objetivo contextualizado con todos los vectores
        all_handles = ", ".join(req.usernames) if req.usernames else target
        all_emails = ", ".join(req.emails) if req.emails else "N/A"
        all_phones = ", ".join(req.phones) if req.phones else "N/A"
        
        objective = (
            f"Investigación exhaustiva de inteligencia del objetivo {target}. "
            f"Handles a correlacionar: [{all_handles}]. "
            f"Emails a investigar: [{all_emails}]. "
            f"Teléfonos a investigar: [{all_phones}]."
        )
        
        try:
            result = await engine.run(
                objective=objective,
                language=lang,
                max_steps=req.max_steps,
                trust_anchors=req.trust_anchors or None,
            )
            session.person = result.person

            # Exportar Canvas dinámico
            safe_name = target.replace("@", "").replace("/", "_").replace("+", "").replace(" ", "_")
            graph = GraphExporter.build_graph(result.person)
            canvas_path = REPORTS_DIR / f"{safe_name}.canvas"
            GraphExporter.export_canvas(graph, canvas_path)
            session.canvas_path = str(canvas_path)

            # Exportar HTML y compilar PDF dinámico con Playwright
            html_path = REPORTS_DIR / f"{safe_name}.html"
            export_person_html(person=result.person, output_path=html_path, language=lang)
            
            pdf_path = REPORTS_DIR / f"{safe_name}_dossier.pdf"
            try:
                from playwright.async_api import async_playwright
                async with async_playwright() as p:
                    browser = await p.chromium.launch()
                    page = await browser.new_page()
                    await page.goto(f"file://{html_path.resolve()}", wait_until="networkidle")
                    await page.pdf(
                        path=str(pdf_path),
                        format="A4",
                        print_background=True,
                        margin={"top": "10mm", "bottom": "10mm", "left": "10mm", "right": "10mm"}
                    )
                    await browser.close()
                session.pdf_path = str(pdf_path)
            except Exception as pdf_err:
                logger.warning("Fallo al generar PDF con Playwright: %s", pdf_err)

            # Emitir todos los nodos confirmados al grafo visual del cliente
            for n in graph.nodes:
                await session.broadcast("node_add", {
                    "id": n.id,
                    "label": n.label,
                    "group": n.type.lower(),
                })
            for e in graph.edges:
                await session.broadcast("edge_add", {
                    "from": e.source,
                    "to": e.target,
                    "label": e.label or e.type,
                })

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
