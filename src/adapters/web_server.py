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


# Nombres de pila muy comunes: buscar "@angel", "@jose", "@maria" produce
# homónimos masivos. Estos NO son identificadores, son nombres propios.
_COMMON_GIVEN_NAMES = {
    "angel", "jose", "maria", "juan", "carlos", "luis", "miguel", "pedro",
    "ana", "laura", "david", "daniel", "javier", "fernando", "ricardo",
    "andres", "alejandro", "pablo", "sergio", "antonio", "francisco",
    "john", "james", "michael", "david", "robert", "mary", "anna", "paul",
    "peter", "mark", "chris", "alex", "sam", "max", "leo", "luca", "hugo",
}

# Prefijos de correo genéricos que no identifican a nadie por sí solos.
_GENERIC_EMAIL_LOCALPARTS = {
    "contacto", "contact", "info", "hello", "hola", "admin", "support",
    "soporte", "ventas", "sales", "mail", "email", "correo", "privacidad",
}


def _is_generic_handle(handle: str, target: str, declared_usernames: list[str]) -> bool:
    """Detects identifiers that are names, not handles (homonym generators).

    Scanning a common given name like "angel" hits hundreds of unrelated people,
    which is exactly the false-positive flood observed with real targets.
    """
    h = (handle or "").strip().lower().lstrip("@")
    if not h:
        return True
    # Si el usuario lo declaró explícitamente como handle, se respeta.
    declared = {(u or "").strip().lower().lstrip("@") for u in declared_usernames}
    if h in declared:
        return False
    # Si es una sola palabra y coincide con un nombre de pila común -> genérico.
    if h in _COMMON_GIVEN_NAMES:
        return True
    # Si coincide con el primer nombre del sujeto -> genérico.
    target_words = [w.lower() for w in (target or "").replace(",", " ").split() if len(w) > 2]
    if target_words and h == target_words[0] and h not in declared:
        return True
    # Muy corto (< 4 chars) y sin dígitos -> poca entropía, probable homónimo.
    if len(h) < 4 and not any(c.isdigit() for c in h):
        return True
    return False


active_sessions: dict[str, InvestigationSession] = {}


def _inject_graph_page_into_html(html_path: Path, graph_png_base64: str, target: str) -> None:
    """Injects a dedicated full-page graph section into the dossier HTML before section 02."""
    html_content = html_path.read_text(encoding="utf-8")

    graph_page = f'''
    <div class="page" id="sec-graph">
      <h2 class="section-title">01.5 // Grafo de Inteligencia Forense</h2>
      <div class="card" style="padding: 12px; background: #070a10; border: 1px solid #1e293b; border-radius: 12px;">
        <div style="color: #00f0ff; font-family: monospace; font-size: 10px; margin-bottom: 10px; font-weight: bold;">
          &gt; TOPOLOG&Iacute;A MULTI-VECTORIAL DE ENTIDADES &mdash; OBJETIVO: {target}
        </div>
        <img src="data:image/png;base64,{graph_png_base64}" style="width: 100%; border-radius: 8px;" alt="Grafo Forense" />
        <p class="muted" style="font-size: 9px; margin-top: 10px;">
          Rojo = Target Ra&iacute;z &bull; Naranja = Identidad Legal &bull; Verde = Alerta OpSec (Tel&eacute;fono/WhatsApp)
          &bull; Amarillo = Correo &bull; Cian = Plataformas y Repos &bull; P&uacute;rpura = Colaborador externo.
        </p>
      </div>
    </div>
'''

    target_tag = '<div class="page" id="sec-02">'
    if target_tag in html_content:
        new_html = html_content.replace(target_tag, graph_page + "\n    " + target_tag)
    else:
        new_html = html_content + graph_page

    html_path.write_text(new_html, encoding="utf-8")


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
        # Registro de correlaciones verificadas durante la corrida.
        correlation_log: list[dict[str, Any]] = []

        def on_step_callback(step: AgentStep):
            asyncio.create_task(session.broadcast("log", f"[PASO {step.step_number}] {step.tool_name} -> {step.tool_args}"))

            # Marca homónimos: buscar "angel" cuando el sujeto se llama Angel
            # produce decenas de falsos positivos. Se anotan, no se dan por ciertos.
            if step.tool_name == "scan_username":
                uname = str(step.tool_args.get("username", "")).strip()
                if not uname:
                    return
                is_generic = _is_generic_handle(uname, target, req.usernames)
                correlation_log.append({
                    "kind": "handle",
                    "value": uname,
                    "generic": is_generic,
                    "step": step.step_number,
                })
                label = f"@{uname}" + (" | falso positivo probable" if is_generic else "")
                asyncio.create_task(session.broadcast("node_add", {
                    "id": f"user:{uname}",
                    "label": label,
                    "group": "noise" if is_generic else "platform",
                }))
            elif step.tool_name == "scan_email":
                em = str(step.tool_args.get("email", "")).strip()
                if em:
                    correlation_log.append({"kind": "email", "value": em, "step": step.step_number})
            elif step.tool_name == "scan_phone":
                ph = str(step.tool_args.get("phone_number", "")).strip()
                if ph:
                    correlation_log.append({"kind": "phone", "value": ph, "step": step.step_number})
            elif step.tool_name == "correlate_stylometry":
                correlation_log.append({
                    "kind": "stylometry",
                    "value": str(step.tool_args.get("sample_text", ""))[:80],
                    "result": str(step.tool_result)[:200],
                    "step": step.step_number,
                })

        await session.broadcast("node_add", {
            "id": "target:root",
            "label": f"{target}",
            "group": "target"
        })

        engine = AgentEngine(settings=settings, enable_breach_check=req.enable_breach_check, on_step=on_step_callback)

        # IMPORTANTE: el nombre del sujeto NUNCA se escanea como handle, porque
        # produce decenas de homónimos (ver _is_generic_handle).
        all_handles = ", ".join(req.usernames) if req.usernames else "N/A (no aportados)"
        all_emails = ", ".join(req.emails) if req.emails else "N/A"
        all_phones = ", ".join(req.phones) if req.phones else "N/A"
        # Las anclas de confianza son la fuente de verdad: si existen, el agente
        # debe partir de ellas y descartar todo lo que no correlacione.
        anchors_line = (
            f"ANCLAS DE CONFIANZA VERIFICADAS (fuente de verdad, priorízalas): [{', '.join(req.trust_anchors)}]. "
            if req.trust_anchors else
            "Sin anclas verificadas: marca toda atribución como NO CONFIRMADA. "
        )
        objective = (
            f"Investigación de inteligencia del sujeto '{target}'. "
            f"{anchors_line}"
            f"Handles a correlacionar: [{all_handles}]. "
            f"Emails a investigar: [{all_emails}]. "
            f"Teléfonos a investigar: [{all_phones}]. "
            "REGLAS ESTRICTAS: (1) '{target}' es un NOMBRE PROPIO, nunca lo uses como handle. "
            "(2) Para cada hallazgo indica el nivel de correlación (confirmado/ probable/ descartado) "
            "y la evidencia concreta que lo sustenta. "
            "(3) Descarta explícitamente los homónimos y explica por qué."
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

            # Renderizar el grafo a PNG de alta resolución para incrustarlo en el PDF
            graph_png_base64 = None
            try:
                graph_png_path = REPORTS_DIR / f"{safe_name}_graph.png"
                GraphExporter.export_graph_png(
                    graph, graph_png_path, title=f"OSINT Intelligence Graph — {target}"
                )
                import base64
                graph_png_base64 = base64.b64encode(graph_png_path.read_bytes()).decode("utf-8")
                await session.broadcast("log", "[GRAFO] Topología de entidades renderizada en alta resolución.")
            except Exception as png_err:
                logger.warning("Fallo al renderizar el grafo a PNG: %s", png_err)

            # Exportar HTML del dossier e inyectar la página dedicada del grafo
            html_path = REPORTS_DIR / f"{safe_name}.html"
            export_person_html(person=result.person, output_path=html_path, language=lang)

            if graph_png_base64:
                _inject_graph_page_into_html(html_path, graph_png_base64, target)

            # Compilar PDF final (diseño HTML + página del grafo) con Playwright
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
                await session.broadcast("log", "[PDF] Dossier compilado con la página del grafo incluida.")
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
