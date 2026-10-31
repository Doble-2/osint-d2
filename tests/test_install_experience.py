"""Installing and starting up without the optional parts."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from adapters import browser, web_server
from cli.main import app
from core.config import AppSettings
from core.domain.language import Language
from core.domain.models import AnalysisReport, PersonEntity
from core.services.agent_engine import AgentResult

REPO = Path(__file__).resolve().parent.parent
runner = CliRunner()


def _doctor(*, http=True, pdf=True, chromium=True):
    with patch("cli.doctor._check_http", new=AsyncMock(return_value=(http, "x"))), \
         patch("cli.doctor._check_pdf", return_value=(pdf, "x")), \
         patch("cli.doctor._check_chromium", return_value=(chromium, "x")):
        return runner.invoke(app, ["doctor", "run"], env={"COLUMNS": "200"})


class TestDoctor:
    def test_missing_optional_parts_are_not_a_failure(self):
        result = _doctor(pdf=False, chromium=False)
        assert result.exit_code == 0
        assert "NOT INSTALLED" in result.output
        assert "doctor install-browser" in result.output

    def test_no_connection_is_still_a_failure(self):
        assert _doctor(http=False).exit_code == 1


class TestChromium:
    def test_install_command_reports_failure(self):
        with patch("cli.doctor.install_chromium", return_value=False):
            assert runner.invoke(app, ["doctor", "install-browser"]).exit_code == 1

    def test_binary_builds_do_not_try_to_install(self):
        with patch.object(sys, "frozen", True, create=True), patch("cli.doctor.install_chromium") as install:
            assert runner.invoke(app, ["doctor", "install-browser"]).exit_code == 1
        install.assert_not_called()

    def test_install_runs_this_python_s_playwright(self):
        with patch("adapters.browser.subprocess.run") as run:
            run.return_value.returncode = 0
            assert browser.install_chromium() is True
        assert run.call_args.args[0] == [sys.executable, "-m", "playwright", "install", "chromium"]


def test_missing_weasyprint_libraries_print_nothing_to_stdout():
    result = subprocess.run(
        [sys.executable, "-c", "import adapters.report_exporter"],
        capture_output=True, text=True, env={"PYTHONPATH": str(REPO / "src"), "PATH": ""},
    )
    assert result.returncode == 0
    assert result.stdout == ""


def test_blank_env_file_values_do_not_hide_saved_ones(tmp_path, monkeypatch):
    monkeypatch.delenv("OSINT_D2_AI_API_KEY", raising=False)
    user, project = tmp_path / "user.env", tmp_path / "project.env"
    user.write_text("OSINT_D2_AI_API_KEY=saved\n", encoding="utf-8")
    project.write_text("OSINT_D2_AI_API_KEY=\n", encoding="utf-8")
    assert AppSettings(_env_file=(user, project)).ai_api_key.get_secret_value() == "saved"


def test_blank_environment_variable_still_clears_the_key(tmp_path, monkeypatch):
    monkeypatch.setenv("OSINT_D2_AI_API_KEY", "")
    saved = tmp_path / "user.env"
    saved.write_text("OSINT_D2_AI_API_KEY=saved\n", encoding="utf-8")
    assert not AppSettings(_env_file=saved).ai_api_key


def test_tests_do_not_read_real_env_files():
    assert AppSettings.model_config["env_file"] is None


class TestMissingChromiumInDashboard:
    async def test_run_finishes_partial_with_the_fix(self, tmp_path, monkeypatch):
        monkeypatch.setattr(web_server, "REPORTS_DIR", tmp_path)
        person = PersonEntity(target="x", analysis=AnalysisReport(summary="ok", highlights=[], confidence=0.5, model="m"))
        session = web_server.InvestigationSession("abc", web_server.InvestigationRequest(target="x"))

        def fake_html(*, output_path, **kwargs):
            output_path.write_text("<html></html>", encoding="utf-8")

        with patch("adapters.web_server._publish_graph", new=AsyncMock()), \
             patch("adapters.web_server.export_person_html", side_effect=fake_html), \
             patch("adapters.web_server.chromium_installed", return_value=False), \
             patch("adapters.web_server._render_pdf", new=AsyncMock()) as render:
            await web_server._export_artifacts(session, AgentResult(person=person), Language.ENGLISH)

        render.assert_not_called()
        assert session.partial is True
        assert any("doctor install-browser" in str(event["data"]) for event in session.events)


class TestSaveKeyFromDashboard:
    def _client(self):
        return TestClient(web_server.app, base_url="http://localhost:8000")

    def test_saves_only_preset_values(self):
        with patch("adapters.web_server.write_user_env_vars") as save:
            response = self._client().post("/api/ai-key", json={"provider": "openai", "api_key": "sk-test"})
        assert response.status_code == 200
        values = save.call_args.args[0]
        assert values["OSINT_D2_AI_API_KEY"] == "sk-test"
        assert values["OSINT_D2_AI_BASE_URL"] == "https://api.openai.com/v1"
        assert "sk-test" not in response.text

    def test_rejects_a_key_that_could_add_settings(self):
        with patch("adapters.web_server.write_user_env_vars") as save:
            response = self._client().post(
                "/api/ai-key", json={"provider": "openai", "api_key": "x\nOSINT_D2_AI_BASE_URL=http://evil"},
            )
        assert response.status_code == 422
        assert "evil" not in response.text
        save.assert_not_called()

    def test_rejects_unknown_provider(self):
        with patch("adapters.web_server.write_user_env_vars") as save:
            assert self._client().post("/api/ai-key", json={"provider": "evil", "api_key": "x"}).status_code == 422
        save.assert_not_called()

    def test_other_websites_cannot_post_it_as_a_simple_form(self):
        with patch("adapters.web_server.write_user_env_vars") as save:
            response = self._client().post(
                "/api/ai-key", content='{"provider":"openai","api_key":"x"}', headers={"content-type": "text/plain"},
            )
        assert response.status_code == 422
        save.assert_not_called()

    def test_reports_when_something_else_overrides_the_key(self, monkeypatch):
        monkeypatch.setenv("OSINT_D2_AI_API_KEY", "from-environment")
        monkeypatch.setenv("OSINT_D2_AI_PROVIDER", "openai")
        with patch("adapters.web_server.write_user_env_vars"):
            response = self._client().post("/api/ai-key", json={"provider": "openai", "api_key": "new"})
        assert response.json() == {"saved": True, "active": False}

    def test_save_failure_does_not_echo_the_key(self):
        with patch("adapters.web_server.write_user_env_vars", side_effect=OSError("disk full")):
            client = TestClient(web_server.app, base_url="http://localhost:8000", raise_server_exceptions=False)
            response = client.post("/api/ai-key", json={"provider": "openai", "api_key": "sk-test"})
        assert response.status_code == 500
        assert "sk-test" not in response.text
