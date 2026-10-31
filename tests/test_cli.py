"""Behaviour of the command-line interface: errors, output and options."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

from cli.main import app
from core.domain.models import PersonEntity

runner = CliRunner(mix_stderr=False)
SRC = Path(__file__).resolve().parent.parent / "src"


def _run_process(*args: str, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "cli.main", *args],
        capture_output=True, text=True, timeout=60,
        env={"PYTHONPATH": str(SRC), "PATH": "/usr/bin:/bin", "HOME": kwargs.pop("home", "/tmp")},
        **kwargs,
    )


def _hunt_result(person: PersonEntity | None = None) -> SimpleNamespace:
    return SimpleNamespace(person=person or PersonEntity(target="x", profiles=[]), usernames=["x"], emails=[])


class TestHelp:
    def test_version(self):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert result.stdout.startswith("osint-d2 ")

    def test_lists_only_real_commands(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        for command in ("agent", "phone", "serve", "hunt"):
            assert command in result.stdout
        assert "breach " not in result.stdout

    @pytest.mark.parametrize("command", ["scan", "scan-email", "hunt", "agent", "phone", "serve", "analyze", "wizard", "doctor"])
    def test_every_command_has_help(self, command):
        assert runner.invoke(app, [command, "--help"]).exit_code == 0


class TestOptionValidation:
    def test_hunt_splits_commas(self):
        with patch("cli.commands.scanning.run_hunt_pipeline", new=AsyncMock(return_value=_hunt_result())) as pipeline:
            result = runner.invoke(app, ["hunt", "-u", "a, b", "-u", "c,a", "-e", "A@x.io,b@y.io", "--format", "json"])

        assert result.exit_code == 0
        request = pipeline.await_args.kwargs["request"]
        assert request.usernames == ["a", "b", "c"]
        assert request.emails == ["a@x.io", "b@y.io"]

    def test_invalid_email_in_list_fails_before_scanning(self):
        with patch("cli.commands.scanning.run_hunt_pipeline", new=AsyncMock()) as pipeline:
            result = runner.invoke(app, ["hunt", "-e", "a@x.io,nope"])
        assert result.exit_code == 2
        pipeline.assert_not_awaited()

    def test_invalid_trust_fails_before_scanning(self):
        with patch("cli.commands.scanning.run_username_pipeline", new=AsyncMock()) as pipeline:
            result = runner.invoke(app, ["scan", "x", "--trust", "badformat"])
        assert result.exit_code == 2
        pipeline.assert_not_awaited()

    @pytest.mark.parametrize("args", [
        ["scan", "x", "--ai-provider", "bogus"],
        ["scan", "x", "--ai-provider", "openai"],
        ["scan", "x", "--deep-analyze", "--ai-key", "k"],
        ["scan", "x", "--proxy", "foo"],
        ["scan", "x", "--proxy-country", "zzzz"],
    ])
    def test_invalid_combinations_are_rejected(self, args):
        with patch("cli.commands.scanning.run_username_pipeline", new=AsyncMock()) as pipeline:
            assert runner.invoke(app, args).exit_code == 2
        pipeline.assert_not_awaited()

    def test_breach_check_requires_key(self, monkeypatch):
        monkeypatch.setenv("OSINT_D2_HIBP_API_KEY", "")
        result = runner.invoke(app, ["hunt", "-e", "a@x.io", "--breach-check"])
        assert result.exit_code == 2

    def test_agent_without_key_explains_on_stderr(self, monkeypatch):
        monkeypatch.setenv("OSINT_D2_AI_PROVIDER", "deepseek")
        monkeypatch.setenv("OSINT_D2_AI_API_KEY", "")
        result = runner.invoke(app, ["agent", "x"])
        assert result.exit_code == 1
        assert result.stdout == ""
        assert "setup-ai" in result.stderr


class TestDataSharing:
    def test_hunt_does_not_call_ai_unless_asked(self):
        with patch("cli.commands.scanning.run_hunt_pipeline", new=AsyncMock(return_value=_hunt_result())), \
             patch("cli.commands.scanning.analyze_person", new=AsyncMock()) as analyze:
            assert runner.invoke(app, ["hunt", "-u", "x", "--format", "json"]).exit_code == 0
        analyze.assert_not_awaited()

    def test_scan_email_does_not_call_ai_unless_asked(self):
        with patch("cli.commands.scanning.run_email_pipeline", new=AsyncMock(return_value=_hunt_result())), \
             patch("cli.commands.scanning.analyze_person", new=AsyncMock()) as analyze:
            assert runner.invoke(app, ["scan-email", "a@x.io", "--format", "json"]).exit_code == 0
        analyze.assert_not_awaited()

    def test_key_is_not_saved_unless_asked(self):
        with patch("cli.commands.scanning.run_username_pipeline", new=AsyncMock(return_value=_hunt_result())), \
             patch("cli.commands.scanning.analyze_person", new=AsyncMock(side_effect=RuntimeError("x"))), \
             patch("cli.shared.write_user_env_vars") as save:
            runner.invoke(app, ["scan", "x", "--deep-analyze", "--ai-provider", "ollama", "--format", "json"])
        save.assert_not_called()


class TestStdoutContract:
    def test_json_is_emitted_once_even_with_ai(self, monkeypatch):
        report = AsyncMock(return_value=SimpleNamespace(model="m"))
        with patch("cli.commands.scanning.run_hunt_pipeline", new=AsyncMock(return_value=_hunt_result())), \
             patch("cli.commands.scanning.analyze_person", new=report), \
             patch.object(PersonEntity, "__setattr__", object.__setattr__):
            result = runner.invoke(app, ["hunt", "-u", "x", "--ai", "--format", "json"])

        assert result.exit_code == 0
        assert json.loads(result.stdout)["target"] == "x"

    def test_explicit_table_is_respected_when_piped(self):
        with patch("cli.commands.scanning.run_username_pipeline", new=AsyncMock(return_value=_hunt_result())):
            result = runner.invoke(app, ["scan", "x", "--format", "table"])
        assert result.exit_code == 0
        with pytest.raises(json.JSONDecodeError):
            json.loads(result.stdout)

    def test_piped_output_defaults_to_json_with_note_on_stderr(self):
        with patch("cli.commands.scanning.run_username_pipeline", new=AsyncMock(return_value=_hunt_result())):
            result = runner.invoke(app, ["scan", "x"])
        assert json.loads(result.stdout)["target"] == "x"
        assert "--format table" in result.stderr


class TestPhone:
    def test_invalid_number_goes_to_stderr(self):
        result = runner.invoke(app, ["phone", "abc", "--format", "json"])
        assert result.exit_code == 1
        assert result.stdout == ""
        assert "Error" in result.stderr


class TestErrorHandling:
    def test_invalid_dossier_is_one_clear_line(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text('{"nope": 1}', encoding="utf-8")
        result = _run_process("analyze", str(bad))
        assert result.returncode == 1
        assert "Traceback" not in result.stderr
        assert "not a valid OSINT-D2 dossier" in result.stderr
        assert len(result.stderr.strip().splitlines()) <= 3

    def test_unexpected_error_never_prints_locals(self):
        code = (
            "import cli.main as m\n"
            "def boom(ai_key='SECRETXYZ123'):\n"
            "    raise RuntimeError('kaput')\n"
            "m._dispatch = lambda: boom()\n"
            "m.run()\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, timeout=60,
            env={"PYTHONPATH": str(SRC), "PATH": "/usr/bin:/bin", "HOME": "/tmp"},
        )
        assert result.returncode == 1
        assert "SECRETXYZ123" not in result.stdout + result.stderr
        assert "kaput" in result.stderr
        assert "Traceback" not in result.stderr

    def test_pretty_exceptions_hide_locals(self):
        assert app.pretty_exceptions_show_locals is False

    def test_ctrl_c_exits_130(self):
        code = (
            "import cli.main as m\n"
            "def boom():\n"
            "    raise KeyboardInterrupt\n"
            "m._dispatch = boom\n"
            "m.run()\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, timeout=60,
            env={"PYTHONPATH": str(SRC), "PATH": "/usr/bin:/bin", "HOME": "/tmp"},
        )
        assert result.returncode == 130


class TestAgentOutput:
    def test_bracketed_model_text_does_not_abort_the_run(self, monkeypatch):
        monkeypatch.setenv("OSINT_D2_AI_API_KEY", "not-a-real-key")
        from core.services.agent_engine import AgentResult, AgentStep

        async def fake_run(self, objective, **kwargs):
            self._on_step(AgentStep(step_number=1, reasoning="closing tag [/foo] from a page"))
            self._on_step(AgentStep(step_number=1, tool_name="fetch_url", tool_args={"url": "[/bar]"}, tool_result="{}"))
            return AgentResult(person=PersonEntity(target="x", profiles=[]))

        with patch("core.services.agent_engine.AgentEngine.run", new=fake_run):
            result = runner.invoke(app, ["agent", "x"])
        assert result.exit_code == 0, result.stderr


class TestDoctor:
    def test_setup_ai_with_blank_key_keeps_the_saved_one(self):
        with patch("cli.doctor.write_user_env_vars", return_value="x") as save:
            result = runner.invoke(app, ["doctor", "setup-ai"], input="deepseek\n\n\n\n")
        assert result.exit_code == 0, result.stderr
        assert "OSINT_D2_AI_API_KEY" not in save.call_args.args[0]

    def test_failed_check_exits_nonzero(self):
        with patch("cli.doctor._check_http", new=AsyncMock(return_value=(False, "down"))), \
             patch("cli.doctor._check_pdf", return_value=(True, "OK")), \
             patch("cli.doctor._check_chromium", return_value=(True, "OK")):
            result = runner.invoke(app, ["doctor", "run"])
        assert result.exit_code == 1
        assert "How to fix" in result.stdout

    def test_healthy_exits_zero_and_mentions_no_private_data(self, monkeypatch):
        monkeypatch.setenv("OSINT_D2_AI_API_KEY", "not-a-real-key")
        with patch("cli.doctor._check_http", new=AsyncMock(return_value=(True, "HTTP 200"))), \
             patch("cli.doctor._check_pdf", return_value=(True, "OK")), \
             patch("cli.doctor._check_chromium", return_value=(True, "OK")):
            result = runner.invoke(app, ["doctor", "run"])
        assert result.exit_code == 0
        assert "not-a-real-key" not in result.stdout
