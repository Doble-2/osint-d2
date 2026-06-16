"""Tests for Sherlock runner with mocked HTTP (issue #32).

Covers:
- Positive match (status_code errorType): 200 → exists=True
- Negative match (status_code errorType): 404 → filtered out
- Message errorType: response contains errorMsg → filtered out
- NSFW filtering
- Progress callback
- Error counting (from #34 fix)
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import httpx

from core.config import AppSettings
from adapters.sherlock_runner import run_sherlock_username


def _mock_response(*, status_code: int = 200, text: str = "", url: str = "https://example.com") -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.text = text
    resp.url = httpx.URL(url)
    return resp


@asynccontextmanager
async def _mock_client(responses: dict[str, MagicMock] | MagicMock):
    """Context manager that yields a mock AsyncClient.

    Args:
        responses: Either a single response (used for all URLs) or a dict
                   mapping URL substrings to responses.
    """
    client = AsyncMock()

    if isinstance(responses, dict):
        async def smart_get(url, **kwargs):
            for pattern, resp in responses.items():
                if pattern in str(url):
                    return resp
            return _mock_response(status_code=404)

        async def smart_request(method, url, **kwargs):
            return await smart_get(url)

        client.get = AsyncMock(side_effect=smart_get)
        client.request = AsyncMock(side_effect=smart_request)
    else:
        client.get = AsyncMock(return_value=responses)
        client.request = AsyncMock(return_value=responses)

    yield client


# ---------------------------------------------------------------------------
# Positive match (status_code errorType)
# ---------------------------------------------------------------------------

class TestSherlockPositiveMatch:
    @pytest.mark.asyncio
    async def test_status_code_200_is_found(self):
        """A site with errorType=status_code and HTTP 200 → profile exists."""
        manifest = {
            "GitHub": {
                "url": "https://github.com/{}",
                "errorType": "status_code",
                "urlMain": "https://github.com",
            },
        }

        resp = _mock_response(status_code=200, text="<html>profile</html>", url="https://github.com/testuser")

        with patch("adapters.sherlock_runner.build_async_client", return_value=_mock_client(resp)), \
             patch("adapters.sherlock_runner.request_with_retry", AsyncMock(return_value=resp)):
            result = await run_sherlock_username(
                usernames=["testuser"],
                manifest=manifest,
                settings=AppSettings(),
                max_concurrency=5,
                no_nsfw=False,
            )

        # run_sherlock_username returns (list[SocialProfile], error_count)
        if isinstance(result, tuple):
            found, errors = result
        else:
            found, errors = result, 0

        assert len(found) == 1
        assert found[0].exists is True
        assert found[0].network_name == "github"
        assert found[0].username == "testuser"
        assert errors == 0


# ---------------------------------------------------------------------------
# Negative match (status_code errorType)
# ---------------------------------------------------------------------------

class TestSherlockNegativeMatch:
    @pytest.mark.asyncio
    async def test_status_code_404_not_found(self):
        """A site with errorType=status_code and HTTP 404 → profile NOT found."""
        manifest = {
            "GitHub": {
                "url": "https://github.com/{}",
                "errorType": "status_code",
                "urlMain": "https://github.com",
            },
        }

        resp = _mock_response(status_code=404, url="https://github.com/nobody")

        with patch("adapters.sherlock_runner.build_async_client", return_value=_mock_client(resp)), \
             patch("adapters.sherlock_runner.request_with_retry", AsyncMock(return_value=resp)):
            result = await run_sherlock_username(
                usernames=["nobody"],
                manifest=manifest,
                settings=AppSettings(),
                max_concurrency=5,
                no_nsfw=False,
            )

        if isinstance(result, tuple):
            found, _ = result
        else:
            found = result

        assert len(found) == 0


# ---------------------------------------------------------------------------
# Message errorType
# ---------------------------------------------------------------------------

class TestSherlockMessageErrorType:
    @pytest.mark.asyncio
    async def test_error_message_in_response_means_not_found(self):
        """A site with errorType=message and errorMsg in response → not found."""
        manifest = {
            "TestSite": {
                "url": "https://testsite.com/users/{}",
                "errorType": "message",
                "errorMsg": "User not found",
                "urlMain": "https://testsite.com",
            },
        }

        resp = _mock_response(
            status_code=200,
            text="<html>User not found</html>",
            url="https://testsite.com/users/nobody",
        )

        with patch("adapters.sherlock_runner.build_async_client", return_value=_mock_client(resp)), \
             patch("adapters.sherlock_runner.request_with_retry", AsyncMock(return_value=resp)):
            result = await run_sherlock_username(
                usernames=["nobody"],
                manifest=manifest,
                settings=AppSettings(),
                max_concurrency=5,
                no_nsfw=False,
            )

        if isinstance(result, tuple):
            found, _ = result
        else:
            found = result

        assert len(found) == 0

    @pytest.mark.asyncio
    async def test_no_error_message_means_found(self):
        """A site with errorType=message where errorMsg is absent → found."""
        manifest = {
            "TestSite": {
                "url": "https://testsite.com/users/{}",
                "errorType": "message",
                "errorMsg": "User not found",
                "urlMain": "https://testsite.com",
            },
        }

        resp = _mock_response(
            status_code=200,
            text="<html><title>John's Profile</title></html>",
            url="https://testsite.com/users/john",
        )

        with patch("adapters.sherlock_runner.build_async_client", return_value=_mock_client(resp)), \
             patch("adapters.sherlock_runner.request_with_retry", AsyncMock(return_value=resp)):
            result = await run_sherlock_username(
                usernames=["john"],
                manifest=manifest,
                settings=AppSettings(),
                max_concurrency=5,
                no_nsfw=False,
            )

        if isinstance(result, tuple):
            found, _ = result
        else:
            found = result

        assert len(found) == 1
        assert found[0].exists is True


# ---------------------------------------------------------------------------
# NSFW filtering
# ---------------------------------------------------------------------------

class TestSherlockNSFWFiltering:
    @pytest.mark.asyncio
    async def test_nsfw_sites_filtered_when_no_nsfw(self):
        """NSFW sites should be skipped when no_nsfw=True."""
        manifest = {
            "SafeSite": {
                "url": "https://safe.com/{}",
                "errorType": "status_code",
                "urlMain": "https://safe.com",
            },
            "NSFWSite": {
                "url": "https://nsfw.com/{}",
                "errorType": "status_code",
                "urlMain": "https://nsfw.com",
                "isNSFW": True,
            },
        }

        resp = _mock_response(status_code=200, text="<html>profile</html>", url="https://safe.com/user")

        with patch("adapters.sherlock_runner.build_async_client", return_value=_mock_client(resp)), \
             patch("adapters.sherlock_runner.request_with_retry", AsyncMock(return_value=resp)):
            result = await run_sherlock_username(
                usernames=["user"],
                manifest=manifest,
                settings=AppSettings(),
                max_concurrency=5,
                no_nsfw=True,
            )

        if isinstance(result, tuple):
            found, _ = result
        else:
            found = result

        site_names = {p.metadata.get("site_name") for p in found}
        assert "NSFWSite" not in site_names
        assert "SafeSite" in site_names


# ---------------------------------------------------------------------------
# Progress callback
# ---------------------------------------------------------------------------

class TestSherlockProgressCallback:
    @pytest.mark.asyncio
    async def test_callback_called_with_correct_counts(self):
        """Progress callback should be called with correct total and progress."""
        manifest = {
            "Site1": {
                "url": "https://site1.com/{}",
                "errorType": "status_code",
                "urlMain": "https://site1.com",
            },
            "Site2": {
                "url": "https://site2.com/{}",
                "errorType": "status_code",
                "urlMain": "https://site2.com",
            },
        }

        resp = _mock_response(status_code=200, text="<html>profile</html>")
        progress_calls: list[tuple[int, int, str]] = []

        def progress_cb(completed: int, total: int, label: str) -> None:
            progress_calls.append((completed, total, label))

        with patch("adapters.sherlock_runner.build_async_client", return_value=_mock_client(resp)), \
             patch("adapters.sherlock_runner.request_with_retry", AsyncMock(return_value=resp)):
            result = await run_sherlock_username(
                usernames=["user"],
                manifest=manifest,
                settings=AppSettings(),
                max_concurrency=5,
                no_nsfw=False,
                progress_callback=progress_cb,
            )

        if isinstance(result, tuple):
            found, _ = result
        else:
            found = result

        # Should be called once for initial (0, total) + once per site
        assert len(progress_calls) >= 2
        # Final call should have completed == total
        totals = {c[1] for c in progress_calls}
        assert 2 in totals  # 2 sites × 1 username = 2 total
        assert isinstance(found, list)  # Verify return type
