"""OSINT-D2 Live Intelligence Web Server (FastAPI + WebSockets).

Features:
1. Real-time WebSocket streaming of agent thoughts and tool executions.
2. Incremental Entity Graph streaming (Vis.js compatible).
3. REST endpoints for launching targets, downloading PDF/Canvas dossiers.
4. Clean Architecture integration: Zero Node.js build steps, pure Python ASGI.
"""

from __future__ import annotations

import asyncio
import base64
import html
import json
import logging
import os
import re
import uuid
from collections.abc import Awaitable, Callable, Coroutine
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
from markupsafe import Markup
from playwright.async_api import Error as PlaywrightError
from pydantic import BaseModel, Field, field_validator

from core import __version__
from core.config import AI_PROVIDER_PRESETS, AppSettings
from core.domain.language import Language
from core.domain.models import PersonEntity
from core.services.agent_engine import AgentEngine, AgentResult, AgentStep
from core.services.agent_prompts import build_objective
from core.services.url_guard import SSRFBlockedError, validate_url
from adapters.chain_builder import ChainBuilder
from adapters.i18n import TEMPLATES_DIR, load_translations
from adapters.graph_exporter import GraphExporter
from adapters.phone_scanner import PhoneScanner
from adapters.radial_graph_renderer import RadialGraphRenderer
from adapters.report_exporter import export_person_html, render_markdown

logger = logging.getLogger(__name__)

app = FastAPI(title="OSINT-D2 Dashboard", version=__version__)

# CORS: locked to localhost by default. Override with OSINT_D2_CORS_ORIGINS
# (comma-separated) for LAN access, e.g. "http://192.168.1.50:8000".
_cors_env = os.getenv("OSINT_D2_CORS_ORIGINS", "").strip()
_allowed_origins = (
    [o.strip() for o in _cors_env.split(",") if o.strip()]
    if _cors_env
    else ["http://localhost:8000", "http://127.0.0.1:8000"]
)

# Una página que apunte su dominio a 127.0.0.1 (DNS rebinding) sería "same-origin"
# con este servidor, que no tiene login: solo se aceptan hosts conocidos.
_allowed_hosts = ["localhost", "127.0.0.1", *(urlparse(o).hostname or "" for o in _allowed_origins)]
_allowed_hosts = sorted({h for h in _allowed_hosts if h})

app.add_middleware(TrustedHostMiddleware, allowed_hosts=_allowed_hosts)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

VENDOR_DIR = TEMPLATES_DIR / "vendor"
REPORTS_DIR = Path("reports")

# Límites del servidor: cada investigación consume créditos de IA y Chromium.
MAX_RUNNING_INVESTIGATIONS = 5
MAX_STORED_SESSIONS = 100

# Serve vendorized JS/CSS (vis-network, Font Awesome) from /static/vendor/
if VENDOR_DIR.is_dir():
    app.mount("/static/vendor", StaticFiles(directory=str(VENDOR_DIR)), name="vendor")


class InvestigationRequest(BaseModel):
    target: str = Field(..., min_length=1, max_length=200, description="Target name or primary identifier.")
    usernames: list[str] = Field(default_factory=list, max_length=50, description="List of usernames/handles to investigate.")
    emails: list[str] = Field(default_factory=list, max_length=50, description="List of email addresses.")
    phones: list[str] = Field(default_factory=list, max_length=20, description="List of phone numbers.")
    trust_anchors: list[str] = Field(default_factory=list, max_length=50, description="Verified trust anchors (e.g. github:username).")
    mode: Literal["agent", "phone"] = Field(default="agent", description="'agent' for autonomous AI, 'phone' for telecom only.")
    ai_provider: str | None = Field(default=None, description="AI provider preset; defaults to the configured one.")
    language: str = Field(default="es", description="Language code: es, en, pt, ar, ru.")
    max_steps: int = Field(default=6, ge=1, le=30, description="Max agent reasoning steps.")
    enable_breach_check: bool = Field(default=False, description="Check data breaches.")

    @field_validator("target")
    @classmethod
    def _target_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("target must not be blank")
        return value

    @field_validator("ai_provider")
    @classmethod
    def _provider_known(cls, value: str | None) -> str | None:
        if value is not None and value not in AI_PROVIDER_PRESETS:
            raise ValueError(f"unknown provider; choose one of: {', '.join(AI_PROVIDER_PRESETS)}")
        return value

    @field_validator("language")
    @classmethod
    def _language_supported(cls, value: str) -> str:
        Language.from_str(value)
        return value


class InvestigationSession:
    def __init__(self, inv_id: str, request: InvestigationRequest):
        self.inv_id = inv_id
        self.request = request
        self.status = "running"
        self.websockets: list[WebSocket] = []
        self.person: PersonEntity | None = None
        self.pdf_path: str | None = None
        self.canvas_path: str | None = None
        self.steps: list[Any] = []
        # Eventos ya emitidos: se reproducen al conectar, porque la investigación
        # arranca antes de que el navegador abra el WebSocket.
        self.events: list[dict[str, Any]] = []
        self.graph_svg_path: str | None = None
        self.graph_png_path: str | None = None
        # Cancelación cooperativa: el bucle del agente consulta este flag.
        self.cancelled: bool = False
        # Fallos no fatales: la investigación termina, pero con resultado parcial.
        self.partial: bool = False
        self.task: asyncio.Task[Any] | None = None

    def t(self, key: str, **values: Any) -> str:
        """Traduce un mensaje al idioma de la investigación."""
        lang_code = Language.from_str(self.request.language).value
        return load_translations(lang_code)[key].format(**values)

    def cancel(self) -> None:
        """Marca la sesión como cancelada; el bucle del agente la detiene."""
        self.cancelled = True
        self.status = "cancelled"
        # Una herramienta colgada nunca llegaría a consultar el flag.
        if self.task is not None:
            self.task.cancel()

    async def broadcast(self, message_type: str, data: Any):
        payload = {"type": message_type, "data": data}
        self.events.append(payload)
        dead_ws = []
        for ws in list(self.websockets):
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

# asyncio solo guarda referencias débiles a las tareas: sin esto el GC puede
# destruir una investigación en curso.
_background_tasks: set[asyncio.Task[Any]] = set()


class _InvestigationCancelled(Exception):
    """Señal interna para abortar una investigación cancelada por el usuario."""


def _spawn(coro: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


def _evict_finished_sessions() -> None:
    """Olvida las sesiones terminadas más antiguas al superar el máximo."""
    excess = len(active_sessions) - MAX_STORED_SESSIONS + 1
    if excess <= 0:
        return
    finished = [k for k, v in active_sessions.items() if v.status != "running"]
    for inv_id in finished[:excess]:
        del active_sessions[inv_id]


def _safe_filename(value: str) -> str:
    """Reduce un identificador libre a un nombre de archivo seguro."""
    return re.sub(r"[^\w.-]+", "_", value).strip("._")[:80] or "target"


def _settings_for_provider(provider: str | None) -> AppSettings:
    """Carga la configuración y aplica el preset si se pide otro proveedor."""
    settings = AppSettings()
    if provider and provider != settings.ai_provider.lower():
        preset = AI_PROVIDER_PRESETS[provider]
        # La key pertenece al proveedor configurado: nunca se envía a otro.
        if not settings.key_belongs_to(provider):
            settings.ai_api_key = None
        settings.ai_provider = provider
        settings.ai_base_url = preset["base_url"]
        settings.ai_model = preset["model"]
    return settings


def _origin_allowed(websocket: WebSocket) -> bool:
    """Evita que una web ajena abra el WebSocket desde el navegador del usuario.

    Se compara con Host porque el puerto es configurable (``serve --port``).
    Los clientes que no son navegadores no envían Origin.
    """
    origin = websocket.headers.get("origin")
    if not origin or origin in _allowed_origins:
        return True
    return urlparse(origin).netloc == websocket.headers.get("host")


def _inject_graph_page_into_html(
    html_path: Path,
    graph_png_base64: str,
    target: str,
    heading: str = "01.5 // Graph",
    caption: str = "",
) -> None:
    """Injects a dedicated full-page figure section into the dossier HTML before section 02."""
    html_content = html_path.read_text(encoding="utf-8")
    target = html.escape(target)
    heading = html.escape(heading)
    caption = html.escape(caption)

    graph_page = f'''
    <div class="page" id="sec-graph">
      <h2 class="section-title">{heading}</h2>
      <div class="card" style="padding: 12px; background: #04120e; border: 1px solid rgba(52,211,153,0.18); border-radius: 12px;">
        <img src="data:image/png;base64,{graph_png_base64}" style="width: 100%; border-radius: 8px;" alt="" />
        <p class="muted" style="font-size: 9px; margin-top: 10px;">
          {caption} &mdash; {target}
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


@app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def get_dashboard(request: Request, lang: str | None = None):
    # HEAD requests: return empty body with correct headers (for healthchecks).
    if request.method == "HEAD":
        return HTMLResponse(content="", status_code=200)
    dashboard_file = TEMPLATES_DIR / "dashboard.html"
    if not dashboard_file.exists():
        raise HTTPException(status_code=404, detail="Dashboard template not found.")

    # ── Load i18n strings ──
    lang_code = (lang or "en").strip().lower()[:2]
    if not (TEMPLATES_DIR / "i18n" / f"{lang_code}.json").exists():
        lang_code = "en"
    t = load_translations(lang_code)

    # ── Render with Jinja2 ──
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    env.filters["tojson"] = lambda v: Markup(json.dumps(v, ensure_ascii=False))
    template = env.get_template("dashboard.html")
    settings = AppSettings()
    return HTMLResponse(content=template.render(
        t=t,
        ui_lang=lang_code,
        text_dir="rtl" if lang_code == "ar" else "ltr",
        ai_provider=settings.ai_provider.lower(),
        ai_key_configured=bool(settings.ai_api_key),
    ))


@app.post("/api/investigate")
async def start_investigation(req: InvestigationRequest):
    running = sum(1 for s in active_sessions.values() if s.status == "running")
    if running >= MAX_RUNNING_INVESTIGATIONS:
        raise HTTPException(status_code=429, detail="Too many investigations running.")

    _evict_finished_sessions()
    inv_id = uuid.uuid4().hex
    session = InvestigationSession(inv_id, req)
    active_sessions[inv_id] = session

    session.task = _spawn(_run_investigation(session))
    return {"investigation_id": inv_id, "status": "started", "target": req.target}


@app.post("/api/cancel/{inv_id}")
async def cancel_investigation(inv_id: str):
    """Cancelación cooperativa de una investigación en curso.

    Nielsen #3 (user control and freedom): el usuario debe poder salir de
    cualquier proceso largo. El bucle del agente consulta session.cancelled.
    """
    session = active_sessions.get(inv_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    if session.status != "running":
        return {"status": session.status, "investigation_id": inv_id}
    session.cancel()
    await session.broadcast("status", "cancelled")
    return {"status": "cancelled", "investigation_id": inv_id}


@app.websocket("/ws/{inv_id}")
async def websocket_stream(websocket: WebSocket, inv_id: str):
    if not _origin_allowed(websocket):
        await websocket.close(code=1008)
        return

    await websocket.accept()
    session = active_sessions.get(inv_id)
    if not session:
        await websocket.send_json({"type": "error", "data": "Investigation not found."})
        await websocket.close()
        return

    try:
        # Sin await entre la última comprobación y el registro: ningún evento
        # puede perderse ni llegar dos veces.
        sent = 0
        while sent < len(session.events):
            await websocket.send_json(session.events[sent])
            sent += 1
        session.websockets.append(websocket)

        while True:
            # Keep alive / listen for client actions
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in session.websockets:
            session.websockets.remove(websocket)


@app.get("/api/download/{inv_id}/{file_type}")
async def download_artefact(inv_id: str, file_type: str):
    session = active_sessions.get(inv_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    safe_name = _safe_filename(session.request.target)

    # Solo se sirven archivos de esta sesión: derivar la ruta del nombre del
    # objetivo daría acceso a informes de investigaciones ajenas.
    if file_type == "canvas":
        path, filename, media_type = session.canvas_path, f"{safe_name}.canvas", "application/json"
    elif file_type == "pdf":
        path, filename, media_type = session.pdf_path, f"dossier_{safe_name}.pdf", "application/pdf"
    else:
        raise HTTPException(status_code=400, detail="Invalid format.")

    if not path or not Path(path).exists():
        raise HTTPException(status_code=404, detail=f"{file_type} not generated yet.")
    return FileResponse(path, filename=filename, media_type=media_type)


async def _run_investigation(session: InvestigationSession) -> None:
    """Ejecuta la investigación y garantiza que el cliente reciba un estado final."""
    try:
        await _execute_investigation(session)
    except (_InvestigationCancelled, asyncio.CancelledError):
        # La tarea se absorbe aquí para poder avisar al cliente.
        await session.broadcast("log", session.t("log_cancelled"))
    except Exception as exc:
        logger.exception("Investigation %s failed", session.inv_id)
        session.status = "failed"
        await session.broadcast("log", f"[ERROR] {exc}")
        await session.broadcast("status", "failed")
    else:
        session.status = "partial" if session.partial else "completed"
        await session.broadcast("status", session.status)


def _raise_if_cancelled(session: InvestigationSession) -> None:
    if session.cancelled:
        raise _InvestigationCancelled()


async def _execute_investigation(session: InvestigationSession) -> None:
    req = session.request
    settings = _settings_for_provider(req.ai_provider)

    await session.broadcast("log", session.t("log_init", target=req.target, mode=req.mode.upper()))
    await _seed_graph(session, settings)
    _raise_if_cancelled(session)

    if req.mode == "agent":
        lang = Language.from_str(req.language)
        result = await _run_agent(session, settings, lang)
        _raise_if_cancelled(session)
        await _export_artifacts(session, result, lang)


async def _seed_graph(session: InvestigationSession, settings: AppSettings) -> None:
    """Publica en el grafo los datos aportados por el usuario."""
    req = session.request

    async def add_linked_node(node_id: str, label: str, group: str, edge_label: str) -> None:
        await session.broadcast("node_add", {"id": node_id, "label": label, "group": group})
        await session.broadcast("edge_add", {"from": "target:root", "to": node_id, "label": edge_label})

    await session.broadcast("node_add", {"id": "target:root", "label": req.target, "group": "target"})

    for phone_num in req.phones:
        _raise_if_cancelled(session)
        await session.broadcast("log", session.t("log_phone", phone=phone_num))
        phone_res = await PhoneScanner.scan(phone_number=phone_num, settings=settings)
        if not phone_res.is_valid:
            session.partial = True
            await session.broadcast("log", session.t("log_phone_invalid", phone=phone_num, error=phone_res.error or ""))
            continue
        await session.broadcast("phone_data", {
            "e164": phone_res.e164,
            "carrier": phone_res.carrier_name,
            "country": phone_res.country_name,
            "line_type": phone_res.line_type,
            "whatsapp": phone_res.whatsapp_active,
            "timezones": phone_res.timezones,
        })
        await add_linked_node(
            f"phone:{phone_res.e164}",
            f"{phone_res.e164}\n({phone_res.carrier_name or 'Tel'})",
            "phone",
            "PHONE_NUM",
        )

    for email in req.emails:
        await add_linked_node(f"email:{email}", email, "email", "USES_EMAIL")

    for anchor in req.trust_anchors:
        await session.broadcast("log", session.t("log_anchor", anchor=anchor))
        await add_linked_node(f"anchor:{anchor}", f"[VERIFIED]\n{anchor}", "identity", "TRUST_ANCHOR")


def _build_objective(req: InvestigationRequest) -> str:
    # IMPORTANTE: el nombre del sujeto NUNCA se escanea como handle, porque
    # produce decenas de homónimos (ver _is_generic_handle).
    return build_objective(
        language=Language.from_str(req.language),
        target=req.target,
        usernames=req.usernames,
        emails=req.emails,
        phones=req.phones,
        trust_anchors=req.trust_anchors,
    )


async def _run_agent(session: InvestigationSession, settings: AppSettings, lang: Language) -> AgentResult:
    req = session.request

    def on_step(step: AgentStep) -> None:
        _raise_if_cancelled(session)
        _spawn(session.broadcast("progress", {"step": step.step_number, "max_steps": req.max_steps}))
        if step.tool_name is None:
            # Los fallos del LLM se informan una sola vez, como error final.
            if step.reasoning and not step.reasoning.startswith("LLM error"):
                _spawn(session.broadcast("log", f"[STEP {step.step_number}] {step.reasoning[:500]}"))
            return

        _spawn(session.broadcast("log", f"[STEP {step.step_number}] {_describe_tool_call(step)}"))

        failure = _tool_failure(step)
        if failure:
            session.partial = True
            _spawn(session.broadcast("log", session.t("log_tool_failed", tool=step.tool_name, error=failure)))

        # Marca homónimos: buscar "angel" cuando el sujeto se llama Angel
        # produce decenas de falsos positivos. Se anotan, no se dan por ciertos.
        if step.tool_name == "scan_username":
            uname = str(step.tool_args.get("username", "")).strip()
            if uname:
                is_generic = _is_generic_handle(uname, req.target, req.usernames)
                _spawn(session.broadcast("node_add", {
                    "id": f"user:{uname}",
                    "label": f"@{uname}" + (f" | {session.t('noise_label')}" if is_generic else ""),
                    "group": "noise" if is_generic else "platform",
                }))

    engine = AgentEngine(settings=settings, enable_breach_check=req.enable_breach_check, on_step=on_step)
    result = await engine.run(
        objective=_build_objective(req),
        language=lang,
        max_steps=req.max_steps,
        trust_anchors=req.trust_anchors or None,
        target=req.target,
    )
    session.person = result.person
    session.steps = list(result.steps)

    # El motor registra los fallos del LLM como un paso de texto y no lanza.
    if not result.finished_naturally:
        reason = next((s.reasoning for s in reversed(result.steps) if s.reasoning), None)
        if not result.person.profiles:
            raise RuntimeError(reason or session.t("log_no_evidence"))
        session.partial = True
        await session.broadcast("log", f"{session.t('log_partial')} {reason or ''}".rstrip())
    return result


def _tool_failure(step: AgentStep) -> str | None:
    """Devuelve el error informado por una herramienta, si lo hubo."""
    try:
        result = json.loads(step.tool_result or "")
    except ValueError:
        return None
    error = result.get("error") if isinstance(result, dict) else None
    return str(error)[:200] if error else None


def _describe_tool_call(step: AgentStep) -> str:
    """Resume una llamada para humanos; el informe final no se repite entero."""
    if step.tool_name == "generate_report":
        return "generate_report"
    args = ", ".join(f"{k}={v}" for k, v in step.tool_args.items())
    return f"{step.tool_name}({args})"[:160]


def _timeline_kind(tool: str) -> str:
    for needle, kind in (
        ("username", "Platform"),
        ("email", "Email"),
        ("phone", "Phone"),
        ("breach", "Breach"),
        ("correlate", "Identity"),
        ("stylometry", "Identity"),
    ):
        if needle in tool:
            return kind
    return "Finding"


async def _publish_graph(session: InvestigationSession, person: PersonEntity, stem: str, lang: Language) -> None:
    """Genera el grafo multi-vector y el hilo, y los envía al cliente.

    Se ejecuta antes de exportar el HTML porque el dossier incluye el PNG.
    """
    target = session.request.target
    chain = ChainBuilder.build_chain(session.steps, target, person, language=lang)
    confidence = person.analysis.confidence if person.analysis else None

    # Un solo render del SVG: sirve al cliente y al PDF
    graph_svg = RadialGraphRenderer.render_svg(chain, target=target, confidence=confidence, language=lang)
    svg_path = REPORTS_DIR / f"{stem}_grafo.svg"
    svg_path.write_text(graph_svg, encoding="utf-8")
    session.graph_svg_path = str(svg_path)

    try:
        session.graph_png_path = await asyncio.to_thread(
            RadialGraphRenderer.export_png,
            chain,
            str(REPORTS_DIR / f"{stem}_grafo.png"),
            target=target,
            confidence=confidence,
            scale=2,
            language=lang,
        )
    except Exception as png_err:
        logger.warning("Fallo al rasterizar el grafo: %s", png_err)

    vector_numbers = (re.search(r"#(\d+)", e.label or "") for e in chain.edges)
    await session.broadcast("graph_svg", {
        "target": target,
        "confidence": confidence,
        "svg": graph_svg,
        "nodes": len(chain.nodes),
        "edges": len(chain.edges),
        "vectors": max((int(m.group(1)) for m in vector_numbers if m), default=1),
    })

    await session.broadcast("timeline", {
        "steps": [
            {
                "kind": _timeline_kind(s.tool_name or ""),
                "label": _describe_tool_call(s),
                "evidence": str(s.tool_result or "")[:500],
                "correlation": None,
            }
            for s in session.steps
            if s.tool_name
        ],
        "confidence": confidence,
    })


def _pdf_request_guard(html_path: Path) -> Callable[[Any], Awaitable[None]]:
    """Limit what Chromium loads while rendering a dossier with third-party data."""
    own_file = html_path.resolve().as_uri()

    async def guard(route: Any) -> None:
        url = route.request.url
        if url.startswith("data:") or url.split("#")[0] == own_file:
            await route.continue_()
            return
        if url.startswith("file:"):
            await route.abort()
            return
        try:
            await asyncio.to_thread(validate_url, url)
            # Playwright does not route redirect hops, so a public image could
            # otherwise redirect the browser to an internal address.
            response = await route.fetch(max_redirects=0)
        except (SSRFBlockedError, ValueError, PlaywrightError):
            await route.abort()
            return
        if 300 <= response.status < 400:
            await route.abort()
            return
        await route.fulfill(response=response)

    return guard


async def _render_pdf(html_path: Path, pdf_path: Path) -> None:
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        # El dossier contiene datos de terceros y no necesita JavaScript.
        context = await browser.new_context(java_script_enabled=False)
        page = await context.new_page()
        await page.route("**/*", _pdf_request_guard(html_path))
        await page.goto(f"file://{html_path.resolve()}", wait_until="networkidle")
        await page.pdf(
            path=str(pdf_path),
            format="A4",
            print_background=True,
            margin={"top": "10mm", "bottom": "10mm", "left": "10mm", "right": "10mm"},
        )
        await browser.close()


async def _export_artifacts(session: InvestigationSession, result: AgentResult, lang: Language) -> None:
    """Genera canvas, grafo y PDF. Los fallos visuales no invalidan la investigación."""
    target = session.request.target
    person = result.person
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    # El id evita que dos investigaciones del mismo objetivo se sobrescriban.
    stem = f"{_safe_filename(target)}_{session.inv_id[:8]}"

    canvas_path = REPORTS_DIR / f"{stem}.canvas"
    GraphExporter.export_canvas(GraphExporter.build_graph(person), canvas_path)
    session.canvas_path = str(canvas_path)
    await session.broadcast("artifact", "canvas")

    if person.analysis:
        await session.broadcast("report_done", {
            "summary": person.analysis.summary,
            "summary_html": render_markdown(person.analysis.summary),
            "highlights": person.analysis.highlights,
            "confidence": person.analysis.confidence,
        })

    try:
        await _publish_graph(session, person, stem, lang)
    except Exception as chain_err:
        logger.warning("Fallo al construir el grafo multi-vector: %s", chain_err)
    _raise_if_cancelled(session)

    html_path = REPORTS_DIR / f"{stem}.html"
    export_person_html(person=person, output_path=html_path, language=lang)

    if session.graph_png_path and Path(session.graph_png_path).exists():
        png_b64 = base64.b64encode(Path(session.graph_png_path).read_bytes()).decode("utf-8")
        _inject_graph_page_into_html(
            html_path, png_b64, target,
            heading=session.t("pdf_graph_heading"),
            caption=session.t("pdf_graph_caption"),
        )
    else:
        await session.broadcast("log", session.t("log_pdf_no_graph"))
    _raise_if_cancelled(session)

    pdf_path = REPORTS_DIR / f"{stem}_dossier.pdf"
    try:
        await _render_pdf(html_path, pdf_path)
        session.pdf_path = str(pdf_path)
        await session.broadcast("artifact", "pdf")
        await session.broadcast("log", session.t("log_pdf_ok"))
    except Exception as pdf_err:
        logger.warning("Fallo al generar PDF con Playwright: %s", pdf_err)
        session.partial = True
        await session.broadcast("log", session.t("log_pdf_error", error=pdf_err))
