"""Regressions found by the repository audit."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from adapters.http_client import MAX_BODY_BYTES, extract_html_metadata, get_limited
from adapters.rate_limiter import DomainRateLimiter
from core.config import AppSettings, write_user_env_vars
from core.domain.models import SocialProfile
from core.services import identity_pipeline
from core.services.agent_engine import AgentEngine
from core.services.identity_pipeline import HuntRequest, _MAX_PIVOTS, hunt


class TestHostilePages:
    def test_long_text_does_not_stall_email_search(self):
        start = time.monotonic()
        extract_html_metadata(html="<p>" + "a" * 200_000 + "</p>")
        assert time.monotonic() - start < 1

    def test_emails_are_still_found(self):
        meta = extract_html_metadata(html='<p>me: ana.b+x@sub.example.com</p><a href="mailto:z@example.org">z</a>')
        assert meta["emails"] == ["ana.b+x@sub.example.com", "z@example.org"]

    @pytest.mark.asyncio
    async def test_body_is_cut_at_the_limit_and_stays_readable(self):
        def endless(request):
            async def body():
                while True:
                    yield b"a" * 65536
            return httpx.Response(200, headers={"content-length": "99"}, content=body())

        async with httpx.AsyncClient(transport=httpx.MockTransport(endless)) as client:
            resp = await get_limited(client, "https://example.com/big")

        assert len(resp.content) == MAX_BODY_BYTES
        assert resp.status_code == 200
        assert str(resp.url) == "https://example.com/big"


class _ChainScanner:
    """Every username reveals a new one, like a hostile profile would."""

    calls: list[str] = []

    async def scan(self, username):
        type(self).calls.append(username)
        return SocialProfile(
            url=f"https://example.com/{username}", username=username, network_name="chain",
            exists=False, metadata={"other_users": [f"{username}x"]},
        )


class _ListsManyEmails:
    async def scan(self, username):
        return SocialProfile(
            url="https://example.com/", username=username, network_name="many", exists=False,
            metadata={"emails": [f"user{i}@example.com" for i in range(20)]},
        )


class _LocalpartScanner:
    calls: list[str] = []

    async def scan(self, value):
        type(self).calls.append(value)
        return SocialProfile(url="https://example.com/", username=value, network_name="n", exists=False)


async def _hunt(scanners, *, usernames=(), emails=()):
    with patch.object(identity_pipeline, "_USERNAME_SCANNERS", scanners), \
         patch.object(identity_pipeline, "_EMAIL_SCANNERS", ()), \
         patch.object(identity_pipeline, "enrich_profiles_from_html", new=AsyncMock()):
        return await hunt(settings=AppSettings(_env_file=None), request=HuntRequest(usernames=usernames, emails=emails))


class TestPipeline:
    @pytest.mark.asyncio
    async def test_pivots_stop_at_the_limit(self):
        _ChainScanner.calls = []
        result = await _hunt((_ChainScanner,), usernames=["a"])
        assert len(_ChainScanner.calls) == _MAX_PIVOTS
        assert any("Pivot limit" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_many_discovered_emails_do_not_lose_the_scan(self):
        with patch.object(identity_pipeline, "_MAX_PIVOTS", 0):
            result = await _hunt((_ListsManyEmails,), usernames=["a"])
        assert len(result.person.target) <= 256

    @pytest.mark.asyncio
    async def test_email_localpart_is_scanned_once(self):
        _LocalpartScanner.calls = []
        await _hunt((_LocalpartScanner,), emails=["ana@example.com"])
        assert _LocalpartScanner.calls == ["ana"]

    @pytest.mark.asyncio
    async def test_overlong_username_failure_is_reported_not_raised(self):
        class Broken:
            async def scan(self, username):
                raise RuntimeError("boom")

        result = await _hunt((Broken,), usernames=["u" * 300])
        assert result.scan_errors == 1


class TestSettings:
    def test_project_env_wins_over_user_env(self):
        # pydantic-settings gives priority to the last file.
        assert AppSettings.model_config["env_file"][-1] == ".env"

    def test_unreadable_user_env_keeps_its_content(self, tmp_path, monkeypatch):
        monkeypatch.setattr("core.config.get_user_env_file", lambda: tmp_path / ".env")
        (tmp_path / ".env").write_bytes(b"KEY=\xff\xfe")
        with pytest.raises(UnicodeDecodeError):
            write_user_env_vars({"OTHER": "x"})
        assert (tmp_path / ".env").read_bytes() == b"KEY=\xff\xfe"


class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_waiting_on_one_domain_does_not_block_another(self):
        limiter = DomainRateLimiter(delay_ms=300, jitter_ms=0)
        async with limiter.throttle("https://slow.example/1"):
            pass
        waiting = asyncio.create_task(limiter._wait_for_slot("slow.example"))
        await asyncio.sleep(0)
        start = time.monotonic()
        async with limiter.throttle("https://other.example/"):
            assert time.monotonic() - start < 0.1
        await waiting


class TestAgentText:
    @pytest.mark.asyncio
    async def test_text_answer_gets_a_new_instruction_and_forced_report_is_not_natural(self):
        from types import SimpleNamespace as NS
        seen = []

        def reply(**kwargs):
            seen.append(kwargs["messages"][-1]["role"])
            message = NS(tool_calls=None, content="thinking")
            return NS(choices=[NS(message=message)])

        llm = AsyncMock()
        llm.chat.completions.create = AsyncMock(side_effect=reply)
        with patch("core.services.agent_engine.AsyncOpenAI", return_value=llm):
            engine = AgentEngine(settings=AppSettings(_env_file=None, ai_api_key="k"))
            engine._collected_profiles.append(SocialProfile(url="https://e.com", username="u", network_name="n"))
            result = await engine.run("x", max_steps=2, target="x")

        assert seen == ["user", "user", "user"]
        assert result.person.analysis is not None
        assert result.finished_naturally is False
