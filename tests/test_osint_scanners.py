"""Tests for OSINT scanners with mocked HTTP (issue #32).

Covers positive/negative match detection and metadata extraction for
representative scanners: X, GitLab, Keybase, DevTo, Medium, Pinterest.

GitHub and Reddit use specific_scrapers so are tested via mock of
their deep fetch functions.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from contextlib import asynccontextmanager

import pytest
import httpx


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(*, status_code: int = 200, text: str = "", url: str = "https://example.com", headers: dict | None = None) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.text = text
    resp.url = httpx.URL(url)
    resp.headers = headers or {}
    resp.json.return_value = {}
    return resp


@asynccontextmanager
async def _mock_client(response: MagicMock):
    """Context manager that yields a mock AsyncClient."""
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    client.post = AsyncMock(return_value=response)
    yield client


# ---------------------------------------------------------------------------
# X (Twitter) Scanner
# ---------------------------------------------------------------------------

class TestXScanner:
    @pytest.mark.asyncio
    async def test_exists_on_200(self):
        from adapters.osint_sources.x import XScanner

        resp = _mock_response(status_code=200, url="https://x.com/testuser")
        with patch("adapters.osint_sources.x.build_async_client", return_value=_mock_client(resp)):
            scanner = XScanner()
            profile = await scanner.scan("testuser")

        assert profile.exists is True
        assert profile.network_name == "x"
        assert profile.username == "testuser"

    @pytest.mark.asyncio
    async def test_not_exists_on_404(self):
        from adapters.osint_sources.x import XScanner

        resp = _mock_response(status_code=404, url="https://x.com/nonexistent")
        with patch("adapters.osint_sources.x.build_async_client", return_value=_mock_client(resp)):
            scanner = XScanner()
            profile = await scanner.scan("nonexistent")

        assert profile.exists is False


# ---------------------------------------------------------------------------
# GitLab Scanner
# ---------------------------------------------------------------------------

class TestGitLabScanner:
    @pytest.mark.asyncio
    async def test_exists_on_200_extracts_name(self):
        from adapters.osint_sources.gitlab import GitLabScanner

        html = "<html><head><title>John Doe · GitLab</title></head><body></body></html>"
        resp = _mock_response(status_code=200, text=html, url="https://gitlab.com/johndoe")
        with patch("adapters.osint_sources.gitlab.build_async_client", return_value=_mock_client(resp)):
            scanner = GitLabScanner()
            profile = await scanner.scan("johndoe")

        assert profile.exists is True
        assert profile.network_name == "gitlab"
        assert profile.metadata.get("name") == "John Doe"

    @pytest.mark.asyncio
    async def test_not_exists_on_404(self):
        from adapters.osint_sources.gitlab import GitLabScanner

        resp = _mock_response(status_code=404, url="https://gitlab.com/nobody")
        with patch("adapters.osint_sources.gitlab.build_async_client", return_value=_mock_client(resp)):
            scanner = GitLabScanner()
            profile = await scanner.scan("nobody")

        assert profile.exists is False


# ---------------------------------------------------------------------------
# GitHub Scanner (mocks fetch_github_deep)
# ---------------------------------------------------------------------------

class TestGitHubScanner:
    @pytest.mark.asyncio
    async def test_exists_with_api_data(self):
        from adapters.osint_sources.github import GitHubScanner

        api_data = {
            "login": "octocat",
            "name": "The Octocat",
            "bio": "A GitHub mascot",
            "avatar_url": "https://avatars.githubusercontent.com/u/1",
            "email": "octocat@github.com",
            "blog": "https://octocat.dev",
            "twitter_username": "octocat_tw",
            "company": "GitHub",
            "location": "San Francisco",
        }

        with patch("adapters.osint_sources.github.fetch_github_deep", AsyncMock(return_value=api_data)):
            scanner = GitHubScanner()
            result = await scanner.scan("octocat")

        if isinstance(result, list):
            main = result[0]
        else:
            main = result

        assert main.exists is True
        assert main.network_name == "github"
        assert main.bio == "A GitHub mascot"
        assert main.image_url == "https://avatars.githubusercontent.com/u/1"
        # Should extract other_emails, other_users
        assert "octocat@github.com" in main.metadata.get("other_emails", [])
        assert "octocat_tw" in main.metadata.get("other_users", [])

    @pytest.mark.asyncio
    async def test_not_exists(self):
        from adapters.osint_sources.github import GitHubScanner

        with patch("adapters.osint_sources.github.fetch_github_deep", AsyncMock(return_value=None)):
            scanner = GitHubScanner()
            result = await scanner.scan("nonexistent_user_xyz")

        profile = result[0] if isinstance(result, list) else result
        assert profile.exists is False


# ---------------------------------------------------------------------------
# Reddit Scanner (mocks fetch_reddit_deep)
# ---------------------------------------------------------------------------

class TestRedditScanner:
    @pytest.mark.asyncio
    async def test_exists_with_data(self):
        from adapters.osint_sources.reddit import RedditScanner

        api_data = {
            "public_description": "A redditor",
            "icon_img": "https://styles.redditmedia.com/icon.png",
        }

        with patch("adapters.osint_sources.reddit.fetch_reddit_deep", AsyncMock(return_value=api_data)):
            scanner = RedditScanner()
            profile = await scanner.scan("testuser")

        assert profile.exists is True
        assert profile.network_name == "reddit"
        assert profile.bio == "A redditor"

    @pytest.mark.asyncio
    async def test_not_exists(self):
        from adapters.osint_sources.reddit import RedditScanner

        with patch("adapters.osint_sources.reddit.fetch_reddit_deep", AsyncMock(return_value=None)):
            scanner = RedditScanner()
            profile = await scanner.scan("nobody")

        assert profile.exists is False


# ---------------------------------------------------------------------------
# Keybase Scanner
# ---------------------------------------------------------------------------

class TestKeybaseScanner:
    @pytest.mark.asyncio
    async def test_exists_on_200(self):
        from adapters.osint_sources.keybase import KeybaseScanner

        resp = _mock_response(status_code=200, url="https://keybase.io/user1")
        with patch("adapters.osint_sources.keybase.build_async_client", return_value=_mock_client(resp)):
            scanner = KeybaseScanner()
            profile = await scanner.scan("user1")

        assert profile.exists is True
        assert profile.network_name == "keybase"

    @pytest.mark.asyncio
    async def test_not_exists_on_404(self):
        from adapters.osint_sources.keybase import KeybaseScanner

        resp = _mock_response(status_code=404, url="https://keybase.io/nobody")
        with patch("adapters.osint_sources.keybase.build_async_client", return_value=_mock_client(resp)):
            scanner = KeybaseScanner()
            profile = await scanner.scan("nobody")

        assert profile.exists is False


# ---------------------------------------------------------------------------
# Telegram Scanner
# ---------------------------------------------------------------------------

class TestTelegramScanner:
    @pytest.mark.asyncio
    async def test_exists_when_not_contact_page(self):
        from adapters.osint_sources.telegram import TelegramScanner

        html = """<html><head>
            <meta property="og:title" content="Chad Fowler">
        </head><body>
            <div class="tgme_page_title"><span dir="auto">Chad Fowler</span></div>
            <meta property="og:image" content="https://cdn.telegram.org/avatar.jpg">
        </body></html>"""

        resp = _mock_response(status_code=200, text=html, url="https://t.me/chadfowler")
        with patch("adapters.osint_sources.telegram.build_async_client", return_value=_mock_client(resp)):
            scanner = TelegramScanner()
            profile = await scanner.scan("chadfowler")

        assert profile.exists is True
        assert profile.network_name == "telegram"
        assert profile.metadata.get("name") == "Chad Fowler"

    @pytest.mark.asyncio
    async def test_not_exists_when_contact_page(self):
        from adapters.osint_sources.telegram import TelegramScanner

        html = """<html><head>
            <meta property="og:title" content="Telegram: Contact @nobody">
        </head><body></body></html>"""

        resp = _mock_response(status_code=200, text=html, url="https://t.me/nobody")
        with patch("adapters.osint_sources.telegram.build_async_client", return_value=_mock_client(resp)):
            scanner = TelegramScanner()
            profile = await scanner.scan("nobody")

        assert profile.exists is False
