"""Regression tests for the security and reliability audit."""

from __future__ import annotations

import json
import os
import stat
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from adapters import web_server
from adapters.report_exporter import _get_env
from adapters.web_server import (
    InvestigationRequest,
    InvestigationSession,
    _build_objective,
    _inject_graph_page_into_html,
    _run_investigation,
    _safe_filename,
    active_sessions,
    app,
)
from core.config import AppSettings, write_user_env_vars
from core.domain.language import Language
from core.domain.models import AnalysisReport, PersonEntity
from core.services.agent_engine import AgentEngine, AgentResult, AgentStep, _parse_confidence
from core.services.agent_tools import execute_tool
from core.services.url_guard import SSRFBlockedError, validate_url

PUBLIC_DNS = [(2, 1, 6, "", ("93.184.216.34", 0))]
client = TestClient(app, base_url="http://localhost")


@pytest.fixture(autouse=True)
def _clean_sessions():
    active_sessions.clear()
    yield
    active_sessions.clear()


def _response(status: int, url: str, *, location: str | None = None, body: str = "") -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status
    resp.url = httpx.URL(url)
    resp.headers = {"location": location} if location else {}
    resp.text = body
    resp.content = b""
    return resp


def _client_returning(*responses: MagicMock):
    http_client = AsyncMock()
    http_client.get = AsyncMock(side_effect=list(responses))

    @asynccontextmanager
    async def factory(*args, **kwargs):
        yield http_client

    return factory, http_client


class TestUrlGuard:
    @pytest.mark.parametrize("url", [
        "http://[::ffff:127.0.0.1]/",
        "http://[::ffff:169.254.169.254]/",
        "http://[64:ff9b::a9fe:a9fe]/",
        "http://[2002:7f00:1::]/",
        "http://224.0.0.1/",
        "http://240.0.0.1/",
        "http://192.0.2.1/",
    ])
    def test_blocks_non_public_addresses(self, url):
        with pytest.raises(SSRFBlockedError):
            validate_url(url)

    @pytest.mark.parametrize("url", ["https://8.8.8.8/", "https://[2606:4700:4700::1111]/"])
    def test_allows_public_addresses(self, url):
        assert validate_url(url) == url


class TestGuardedFetch:
    @pytest.mark.asyncio
    async def test_fetch_url_blocks_redirect_to_metadata(self):
        factory, http_client = _client_returning(
            _response(302, "https://evil.example/", location="http://169.254.169.254/latest/meta-data/"),
        )
        with patch("core.services.url_guard.socket.getaddrinfo", return_value=PUBLIC_DNS), \
             patch("adapters.http_client.build_async_client", factory):
            result = json.loads(await execute_tool("fetch_url", {"url": "https://evil.example/"}, settings=AppSettings()))

        assert "SSRF blocked" in result["error"]
        assert http_client.get.await_count == 1

    @pytest.mark.asyncio
    async def test_fetch_url_follows_public_relative_redirect(self):
        factory, _ = _client_returning(
            _response(301, "https://site.example/a", location="/b"),
            _response(200, "https://site.example/b", body="<title>Fin</title>"),
        )
        with patch("core.services.url_guard.socket.getaddrinfo", return_value=PUBLIC_DNS), \
             patch("adapters.http_client.build_async_client", factory):
            result = json.loads(await execute_tool("fetch_url", {"url": "https://site.example/a"}, settings=AppSettings()))

        assert result["url"] == "https://site.example/b"
        assert result["title"] == "Fin"

    @pytest.mark.asyncio
    async def test_fetch_url_stops_redirect_loops(self):
        factory, _ = _client_returning(
            *[_response(302, "https://site.example/", location="/") for _ in range(6)],
        )
        with patch("core.services.url_guard.socket.getaddrinfo", return_value=PUBLIC_DNS), \
             patch("adapters.http_client.build_async_client", factory):
            result = json.loads(await execute_tool("fetch_url", {"url": "https://site.example/"}, settings=AppSettings()))

        assert "Too many redirects" in result["error"]

    @pytest.mark.asyncio
    async def test_compare_avatars_blocks_internal_urls(self):
        factory, http_client = _client_returning()
        with patch("adapters.http_client.build_async_client", factory):
            result = json.loads(await execute_tool(
                "compare_avatars",
                {"avatar_url_1": "http://127.0.0.1:6379/", "avatar_url_2": "http://10.0.0.1/"},
                settings=AppSettings(),
            ))

        assert "SSRF blocked" in result["error"]
        http_client.get.assert_not_awaited()


class TestDossierMarkdown:
    def _render(self, text: str) -> str:
        return str(_get_env().filters["markdown"](text))

    def test_raw_html_is_escaped(self):
        rendered = self._render("hola <script>alert(1)</script>\n\n<img src=x onerror=alert(1)>")
        assert "<script" not in rendered
        assert "<img" not in rendered
        assert "&lt;script&gt;" in rendered

    @pytest.mark.parametrize("link", ["javascript:alert(1)", "&#106;avascript:alert(1)", "data:text/html,x"])
    def test_unsafe_links_are_neutralized(self, link):
        assert 'href="#"' in self._render(f"[click]({link})")

    def test_regular_markdown_still_works(self):
        rendered = self._render("# Título\n\n> cita\n\n**negrita** [web](https://example.com)\n\n```\na < b\n```")
        assert "<h1>" in rendered
        assert "<blockquote>" in rendered
        assert "<strong>negrita</strong>" in rendered
        assert 'href="https://example.com"' in rendered
        assert "a &lt; b" in rendered


class TestAgentEngine:
    @pytest.mark.parametrize(("value", "expected"), [
        (0.8, 0.8), ("0.3", 0.3), (7, 1.0), (-2, 0.0), ("high", 0.5), (None, 0.5), (float("nan"), 0.5),
    ])
    def test_parse_confidence(self, value, expected):
        assert _parse_confidence(value) == expected

    def test_duplicate_profiles_are_merged_preferring_confirmed(self):
        engine = AgentEngine(settings=AppSettings())
        entry = {"url": "https://github.com/x", "username": "X", "network": "github"}
        for exists in (False, True, True):
            engine._collect_profiles_from_result(json.dumps({"profiles": [{**entry, "exists": exists}]}))

        assert len(engine._collected_profiles) == 1
        assert engine._collected_profiles[0].exists is True


class TestRequestValidation:
    @pytest.mark.parametrize("override", [
        {"target": ""},
        {"target": "   "},
        {"target": "x" * 201},
        {"max_steps": 0},
        {"max_steps": 1000},
        {"mode": "hunt"},
        {"ai_provider": "evil"},
        {"language": "xx"},
    ])
    def test_invalid_payloads_are_rejected(self, override):
        assert client.post("/api/investigate", json={"target": "x", **override}).status_code == 422

    def test_too_many_running_investigations(self):
        for i in range(web_server.MAX_RUNNING_INVESTIGATIONS):
            active_sessions[str(i)] = InvestigationSession(str(i), InvestigationRequest(target="x"))
        assert client.post("/api/investigate", json={"target": "x"}).status_code == 429

    def test_finished_sessions_are_evicted(self):
        for i in range(web_server.MAX_STORED_SESSIONS):
            session = InvestigationSession(str(i), InvestigationRequest(target="x"))
            session.status = "completed"
            active_sessions[str(i)] = session

        with patch("adapters.web_server._run_investigation", new=AsyncMock()):
            assert client.post("/api/investigate", json={"target": "x"}).status_code == 200
        assert len(active_sessions) == web_server.MAX_STORED_SESSIONS
        assert "0" not in active_sessions

    def test_cancel_unknown_session_returns_404(self):
        assert client.post("/api/cancel/nope").status_code == 404


class TestInvestigationLifecycle:
    @pytest.mark.asyncio
    async def test_failure_reaches_the_client(self):
        session = InvestigationSession("id", InvestigationRequest(target="x"))
        with patch("adapters.web_server._execute_investigation", side_effect=ValueError("no key")):
            await _run_investigation(session)

        assert session.status == "failed"
        assert {"type": "status", "data": "failed"} in session.events
        assert {"type": "log", "data": "[ERROR] no key"} in session.events

    @pytest.mark.asyncio
    async def test_phone_mode_completes(self):
        session = InvestigationSession("id", InvestigationRequest(target="x", mode="phone"))
        await _run_investigation(session)

        assert session.status == "completed"
        assert session.events[-1] == {"type": "status", "data": "completed"}

    @pytest.mark.asyncio
    async def test_graph_edges_reference_an_existing_root(self):
        session = InvestigationSession("id", InvestigationRequest(target="x", mode="phone", emails=["a@b.co"]))
        await _run_investigation(session)

        node_ids = {e["data"]["id"] for e in session.events if e["type"] == "node_add"}
        edges = [e["data"] for e in session.events if e["type"] == "edge_add"]
        assert edges
        assert all(edge["from"] in node_ids and edge["to"] in node_ids for edge in edges)

    def test_objective_interpolates_target(self):
        objective = _build_objective(InvestigationRequest(target="Ada Lovelace"))
        assert "{target}" not in objective
        assert "'Ada Lovelace' es un NOMBRE PROPIO" in objective


class TestProviderSwitch:
    def test_api_key_is_never_sent_to_another_provider(self, monkeypatch):
        monkeypatch.setenv("OSINT_D2_AI_PROVIDER", "deepseek")
        monkeypatch.setenv("OSINT_D2_AI_API_KEY", "deepseek-key")
        settings = web_server._settings_for_provider("openai")
        assert settings.ai_base_url == "https://api.openai.com/v1"
        assert settings.ai_api_key is None

    def test_configured_provider_keeps_its_settings(self, monkeypatch):
        monkeypatch.setenv("OSINT_D2_AI_PROVIDER", "ollama")
        monkeypatch.setenv("OSINT_D2_AI_BASE_URL", "http://ollama:11434/v1")
        monkeypatch.setenv("OSINT_D2_AI_MODEL", "custom")
        settings = web_server._settings_for_provider("ollama")
        assert settings.ai_base_url == "http://ollama:11434/v1"
        assert settings.ai_model == "custom"


class TestLogLanguage:
    @pytest.mark.parametrize(("language", "expected"), [("en", "Target set"), ("es", "Objetivo inicializado"), ("ru", "Цель задана")])
    def test_session_logs_follow_investigation_language(self, language, expected):
        session = InvestigationSession("a", InvestigationRequest(target="x", language=language))
        assert expected in session.t("log_init", target="x", mode="AGENT")

    def test_report_arguments_are_not_repeated_in_logs(self):
        step = AgentStep(step_number=1, tool_name="generate_report", tool_args={"summary": "x" * 5000})
        assert web_server._describe_tool_call(step) == "generate_report"


class TestArtifactEvents:
    @pytest.mark.asyncio
    async def test_announces_only_generated_artifacts_and_sanitizes_report(self, tmp_path, monkeypatch):
        monkeypatch.setattr(web_server, "REPORTS_DIR", tmp_path)
        person = PersonEntity(target="x", profiles=[], analysis=AnalysisReport(
            summary="**ok** <script>alert(1)</script>", highlights=[], confidence=0.5, model="m",
        ))
        session = InvestigationSession("abc", InvestigationRequest(target="x"))

        def fake_html(*, output_path, **kwargs):
            output_path.write_text("<html></html>", encoding="utf-8")

        with patch("adapters.web_server._publish_graph", new=AsyncMock()), \
             patch("adapters.web_server.export_person_html", side_effect=fake_html), \
             patch("adapters.web_server._render_pdf", new=AsyncMock(side_effect=RuntimeError("no chromium"))):
            await web_server._export_artifacts(session, AgentResult(person=person), Language.ENGLISH)

        artifacts = [e["data"] for e in session.events if e["type"] == "artifact"]
        assert artifacts == ["canvas"]
        report = next(e["data"] for e in session.events if e["type"] == "report_done")
        assert "<strong>ok</strong>" in report["summary_html"]
        assert "<script" not in report["summary_html"]


class TestWebSocket:
    def _session(self) -> InvestigationSession:
        session = InvestigationSession("abc", InvestigationRequest(target="x"))
        session.events.append({"type": "log", "data": "early"})
        active_sessions["abc"] = session
        return session

    def test_replays_events_emitted_before_connecting(self):
        self._session()
        with client.websocket_connect("/ws/abc", headers={"host": "localhost"}) as ws:
            assert ws.receive_json() == {"type": "log", "data": "early"}

    def test_rejects_foreign_origin(self):
        from starlette.websockets import WebSocketDisconnect

        self._session()
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws/abc", headers={"origin": "https://evil.example", "host": "localhost"}):
                pass

    def test_accepts_same_origin_on_custom_port(self):
        self._session()
        headers = {"origin": "http://localhost:9000", "host": "localhost:9000"}
        with client.websocket_connect("/ws/abc", headers=headers) as ws:
            assert ws.receive_json()["data"] == "early"


class TestDownloads:
    def test_never_serves_files_of_other_sessions(self, tmp_path, monkeypatch):
        monkeypatch.setattr(web_server, "REPORTS_DIR", tmp_path)
        (tmp_path / "victim_dossier.pdf").write_bytes(b"secret")
        active_sessions["attacker"] = InvestigationSession("attacker", InvestigationRequest(target="victim"))

        assert client.get("/api/download/attacker/pdf").status_code == 404

    def test_serves_own_file(self, tmp_path):
        pdf = tmp_path / "own.pdf"
        pdf.write_bytes(b"%PDF")
        session = InvestigationSession("mine", InvestigationRequest(target="x"))
        session.pdf_path = str(pdf)
        active_sessions["mine"] = session

        response = client.get("/api/download/mine/pdf")
        assert response.status_code == 200
        assert response.content == b"%PDF"

    def test_invalid_format(self):
        active_sessions["s"] = InvestigationSession("s", InvestigationRequest(target="x"))
        assert client.get("/api/download/s/exe").status_code == 400


class TestFilesAndMarkup:
    @pytest.mark.parametrize("value", ["../../etc/passwd", "..\\..\\win", "a/b c@d", "...", ""])
    def test_safe_filename_cannot_escape_directory(self, value):
        name = _safe_filename(value)
        assert name
        assert "/" not in name and "\\" not in name
        assert not name.startswith(".")

    def test_injected_graph_page_escapes_target(self, tmp_path: Path):
        page = tmp_path / "d.html"
        page.write_text('<div class="page" id="sec-02"></div>', encoding="utf-8")
        _inject_graph_page_into_html(page, "AAAA", "<script>alert(1)</script>")

        content = page.read_text(encoding="utf-8")
        assert "<script>" not in content
        assert "&lt;script&gt;" in content

    @pytest.mark.skipif(os.name == "nt", reason="POSIX permissions")
    def test_user_env_file_is_private(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        path = write_user_env_vars({"OSINT_D2_AI_API_KEY": "secret"})
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


class TestPartialResults:
    @pytest.mark.asyncio
    async def test_non_fatal_failure_reports_partial_status(self):
        session = InvestigationSession("id", InvestigationRequest(target="x", mode="phone"))
        session.partial = True
        await _run_investigation(session)
        assert session.status == "partial"
        assert session.events[-1] == {"type": "status", "data": "partial"}

    def test_detects_tool_errors(self):
        failed = AgentStep(step_number=1, tool_name="fetch_url", tool_result='{"error": "HTTP 500"}')
        fine = AgentStep(step_number=1, tool_name="fetch_url", tool_result='{"title": "ok"}')
        assert web_server._tool_failure(failed) == "HTTP 500"
        assert web_server._tool_failure(fine) is None


class TestCancellation:
    @pytest.mark.asyncio
    async def test_cancel_stops_a_hung_tool(self):
        import asyncio

        async def hang(session):
            await asyncio.Event().wait()

        session = InvestigationSession("id", InvestigationRequest(target="x"))
        with patch("adapters.web_server._execute_investigation", new=hang):
            session.task = asyncio.create_task(_run_investigation(session))
            await asyncio.sleep(0)
            session.cancel()
            await asyncio.wait_for(session.task, timeout=2)

        assert session.status == "cancelled"
        assert {"type": "log", "data": session.t("log_cancelled")} in session.events


class TestProviderPresets:
    def test_provider_without_url_uses_its_own_endpoint(self, monkeypatch):
        monkeypatch.setenv("OSINT_D2_AI_PROVIDER", "openai")
        monkeypatch.delenv("OSINT_D2_AI_BASE_URL", raising=False)
        monkeypatch.delenv("OSINT_D2_AI_MODEL", raising=False)
        settings = AppSettings(_env_file=None)
        assert settings.ai_base_url == "https://api.openai.com/v1"
        assert settings.ai_model == "gpt-4o-mini"

    def test_explicit_url_wins(self, monkeypatch):
        monkeypatch.setenv("OSINT_D2_AI_PROVIDER", "ollama")
        monkeypatch.setenv("OSINT_D2_AI_BASE_URL", "http://ollama:11434/v1")
        assert AppSettings(_env_file=None).ai_base_url == "http://ollama:11434/v1"


class TestDnsRebinding:
    def test_unknown_host_is_rejected(self):
        response = client.get("/", headers={"host": "attacker.example:8000"})
        assert response.status_code == 400

    def test_loopback_with_custom_port_is_accepted(self):
        assert client.get("/", headers={"host": "127.0.0.1:9000"}).status_code == 200


class TestReviewFindings:
    def test_other_presets_are_accepted_and_offered(self, monkeypatch):
        monkeypatch.setenv("OSINT_D2_AI_PROVIDER", "groq")
        monkeypatch.setenv("OSINT_D2_AI_API_KEY", "not-a-real-key")
        assert '<option value="groq" selected>' in client.get("/").text
        settings = web_server._settings_for_provider("groq")
        assert settings.ai_api_key is not None
        with patch("adapters.web_server._run_investigation", new=AsyncMock()):
            assert client.post("/api/investigate", json={"target": "x", "ai_provider": "groq"}).status_code == 200

    def test_blank_key_counts_as_missing(self, monkeypatch):
        monkeypatch.setenv("OSINT_D2_AI_API_KEY", "")
        assert "const AI_KEY_CONFIGURED = false;" in client.get("/").text

    @pytest.mark.asyncio
    async def test_invalid_phone_is_reported_without_a_node(self):
        session = InvestigationSession("id", InvestigationRequest(target="x", mode="phone", phones=["abc"]))
        await _run_investigation(session)
        assert session.status == "partial"
        assert not any(e["type"] == "phone_data" for e in session.events)
        assert not any(e["type"] == "node_add" and e["data"]["id"].startswith("phone:") for e in session.events)

    @pytest.mark.asyncio
    async def test_failed_breach_lookup_is_an_error_for_the_agent(self, monkeypatch):
        monkeypatch.setenv("OSINT_D2_HIBP_API_KEY", "")
        result = json.loads(await execute_tool(
            "breach_check", {"email": "a@example.com"}, settings=AppSettings(hibp_api_key=None), enable_breach_check=True,
        ))
        assert "hibp_api_key_missing" in result["error"]

    @pytest.mark.asyncio
    async def test_non_object_tool_arguments_do_not_abort_the_run(self):
        call = SimpleNamespace(id="c1", function=SimpleNamespace(name="scan_username", arguments="[1]"))
        message = SimpleNamespace(tool_calls=[call], content=None, model_dump=lambda: {"role": "assistant"})
        llm = MagicMock()
        llm.chat.completions.create = AsyncMock(return_value=SimpleNamespace(choices=[SimpleNamespace(message=message)]))
        steps = []
        with patch("core.services.agent_engine.AsyncOpenAI", return_value=llm):
            engine = AgentEngine(settings=AppSettings(ai_api_key="k"), on_step=lambda s: steps.append(web_server._describe_tool_call(s)))
            await engine.run("x", max_steps=1)
        assert steps and steps[0].startswith("scan_username(raw=")

    def test_rich_markup_in_reasoning_does_not_crash_the_agent_view(self):
        from rich.console import Console
        from rich.markup import escape

        Console(file=open("/dev/null", "w")).print(f"[italic dim]{escape('[/foo] text')}[/italic dim]")


class TestPdfFetchGuards:
    def _fetcher(self, tmp_path):
        from adapters.report_exporter import _guarded_url_fetcher

        return _guarded_url_fetcher(tmp_path)

    def test_blocks_local_files_outside_templates(self, tmp_path):
        pytest.importorskip("weasyprint")
        with pytest.raises(ValueError):
            self._fetcher(tmp_path).fetch("file:///etc/passwd")

    def test_blocks_internal_addresses(self, tmp_path):
        pytest.importorskip("weasyprint")
        with pytest.raises(SSRFBlockedError):
            self._fetcher(tmp_path).fetch("http://169.254.169.254/latest/meta-data/")

    def test_markdown_image_cannot_reach_internal_address_during_export(self, tmp_path, monkeypatch):
        pytest.importorskip("weasyprint")
        from adapters.report_exporter import export_person_pdf
        from core.domain.language import Language
        from core.domain.models import AnalysisReport, PersonEntity

        fetched = []
        import urllib.request

        real_open = urllib.request.OpenerDirector.open
        monkeypatch.setattr(urllib.request.OpenerDirector, "open", lambda self, req, *a, **k: fetched.append(getattr(req, "full_url", req)) or real_open(self, req, *a, **k))
        person = PersonEntity(target="x", profiles=[], analysis=AnalysisReport(
            summary="![a](http://169.254.169.254/x.png)", highlights=[], confidence=0.5, model="m",
        ))
        export_person_pdf(person=person, output_path=tmp_path / "x.pdf", language=Language.ENGLISH)
        assert not [u for u in fetched if "169.254" in str(u)]
