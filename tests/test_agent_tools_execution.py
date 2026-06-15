"""Tests for execute_tool() dispatch logic (issue #32).

Covers:
- scan_username dispatch
- scan_email dispatch
- breach_check disabled/enabled
- fetch_url with mocked HTTP
- fetch_url invalid scheme
- generate_report echo
- Unknown tool error
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.config import AppSettings
from core.domain.models import PersonEntity, SocialProfile
from core.services.agent_tools import execute_tool
from core.services.identity_pipeline import PipelineResult


def _settings() -> AppSettings:
    return AppSettings()


def _pipeline_result(profiles: list[SocialProfile] | None = None) -> PipelineResult:
    profs = profiles or [
        SocialProfile(
            url="https://github.com/testuser",
            username="testuser",
            network_name="github",
            exists=True,
            metadata={"source": "test"},
        ),
    ]
    return PipelineResult(
        person=PersonEntity(target="test", profiles=profs),
        usernames=["testuser"],
        emails=[],
    )


# ---------------------------------------------------------------------------
# scan_username
# ---------------------------------------------------------------------------

class TestExecuteToolScanUsername:
    @pytest.mark.asyncio
    async def test_returns_json_with_profiles(self):
        mock_scan = AsyncMock(return_value=_pipeline_result())

        with patch("core.services.agent_tools.scan_username", mock_scan):
            result = await execute_tool(
                "scan_username",
                {"username": "testuser"},
                settings=_settings(),
            )

        data = json.loads(result)
        assert data["target"] == "testuser"
        assert "profiles" in data
        assert data["confirmed"] >= 1

    @pytest.mark.asyncio
    async def test_empty_username_returns_error(self):
        result = await execute_tool(
            "scan_username",
            {"username": ""},
            settings=_settings(),
        )
        data = json.loads(result)
        assert "error" in data


# ---------------------------------------------------------------------------
# scan_email
# ---------------------------------------------------------------------------

class TestExecuteToolScanEmail:
    @pytest.mark.asyncio
    async def test_returns_json_with_profiles(self):
        mock_scan = AsyncMock(return_value=_pipeline_result())

        with patch("core.services.agent_tools.scan_email", mock_scan):
            result = await execute_tool(
                "scan_email",
                {"email": "test@test.com"},
                settings=_settings(),
            )

        data = json.loads(result)
        assert data["target"] == "test@test.com"

    @pytest.mark.asyncio
    async def test_empty_email_returns_error(self):
        result = await execute_tool(
            "scan_email",
            {"email": ""},
            settings=_settings(),
        )
        data = json.loads(result)
        assert "error" in data


# ---------------------------------------------------------------------------
# breach_check
# ---------------------------------------------------------------------------

class TestExecuteToolBreachCheck:
    @pytest.mark.asyncio
    async def test_disabled_returns_error(self):
        result = await execute_tool(
            "breach_check",
            {"email": "test@test.com"},
            settings=_settings(),
            enable_breach_check=False,
        )
        data = json.loads(result)
        assert "error" in data
        assert "disabled" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_enabled_returns_results(self):
        breach_profiles = [
            SocialProfile(
                url="https://haveibeenpwned.com/test@test.com",
                username="test@test.com",
                network_name="hibp",
                exists=True,
                metadata={"breaches": {"breach1": {"date": "2020-01-01"}}},
            )
        ]
        mock_breach = MagicMock(return_value=breach_profiles)

        with patch("core.services.agent_tools.enrich_profiles_with_breach_data", mock_breach):
            result = await execute_tool(
                "breach_check",
                {"email": "test@test.com"},
                settings=_settings(),
                enable_breach_check=True,
            )

        data = json.loads(result)
        assert data["target"] == "test@test.com"
        assert "results" in data

    @pytest.mark.asyncio
    async def test_empty_email_returns_error(self):
        result = await execute_tool(
            "breach_check",
            {"email": ""},
            settings=_settings(),
            enable_breach_check=True,
        )
        data = json.loads(result)
        assert "error" in data


# ---------------------------------------------------------------------------
# fetch_url
# ---------------------------------------------------------------------------

class TestExecuteToolFetchUrl:
    @pytest.mark.asyncio
    async def test_successful_fetch(self):
        import httpx
        from contextlib import asynccontextmanager

        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 200
        resp.text = "<html><head><title>Test Page</title><meta name='description' content='A test'></head><body></body></html>"
        resp.url = httpx.URL("https://example.com")

        @asynccontextmanager
        async def mock_client_cm(*args, **kwargs):
            client = AsyncMock()
            client.get = AsyncMock(return_value=resp)
            yield client

        with patch("adapters.http_client.build_async_client", mock_client_cm):
            result = await execute_tool(
                "fetch_url",
                {"url": "https://example.com"},
                settings=_settings(),
            )

        data = json.loads(result)
        assert data["status_code"] == 200
        assert "title" in data or "error" not in data

    @pytest.mark.asyncio
    async def test_prepends_https(self):
        """URLs without scheme get https:// prepended."""
        import httpx
        from contextlib import asynccontextmanager

        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 200
        resp.text = "<html><head><title>Test</title></head></html>"
        resp.url = httpx.URL("https://example.com")

        @asynccontextmanager
        async def mock_client_cm(*args, **kwargs):
            client = AsyncMock()
            client.get = AsyncMock(return_value=resp)
            yield client

        with patch("adapters.http_client.build_async_client", mock_client_cm):
            result = await execute_tool(
                "fetch_url",
                {"url": "example.com"},
                settings=_settings(),
            )

        data = json.loads(result)
        assert "error" not in data

    @pytest.mark.asyncio
    async def test_empty_url_returns_error(self):
        result = await execute_tool(
            "fetch_url",
            {"url": ""},
            settings=_settings(),
        )
        data = json.loads(result)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_http_error_status(self):
        import httpx
        from contextlib import asynccontextmanager

        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 500
        resp.url = httpx.URL("https://example.com")

        @asynccontextmanager
        async def mock_client_cm(*args, **kwargs):
            client = AsyncMock()
            client.get = AsyncMock(return_value=resp)
            yield client

        with patch("adapters.http_client.build_async_client", mock_client_cm):
            result = await execute_tool(
                "fetch_url",
                {"url": "https://example.com"},
                settings=_settings(),
            )

        data = json.loads(result)
        assert "error" in data
        assert "500" in data["error"]


# ---------------------------------------------------------------------------
# generate_report
# ---------------------------------------------------------------------------

class TestExecuteToolGenerateReport:
    @pytest.mark.asyncio
    async def test_echo_response(self):
        result = await execute_tool(
            "generate_report",
            {"summary": "test", "highlights": ["a"], "confidence": 0.9},
            settings=_settings(),
        )
        data = json.loads(result)
        assert data["status"] == "report_generated"


# ---------------------------------------------------------------------------
# Unknown tool
# ---------------------------------------------------------------------------

class TestExecuteToolUnknown:
    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error(self):
        result = await execute_tool(
            "nonexistent_tool",
            {},
            settings=_settings(),
        )
        data = json.loads(result)
        assert "error" in data
        assert "Unknown tool" in data["error"]
