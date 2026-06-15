"""Tests for resources_loader (issue #32).

Covers:
- load_sherlock_data() cached path (no network)
- load_sherlock_data() download path (mocked httpx)
- load_sherlock_data() download failure propagates
- get_default_list_path() returns existing file
- get_default_list_path() returns None when missing
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.resources_loader import load_sherlock_data, get_default_list_path


# ---------------------------------------------------------------------------
# load_sherlock_data — cached path
# ---------------------------------------------------------------------------

class TestLoadSherlockCached:
    def test_loads_from_cache(self, tmp_path: Path):
        """When sherlock.json exists and refresh=False, loads from cache."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        cache_file = data_dir / "sherlock.json"
        expected = {"TestSite": {"url": "http://test/{}", "errorType": "status_code"}}
        cache_file.write_text(json.dumps(expected), encoding="utf-8")

        with patch("core.resources_loader._data_dir", return_value=data_dir):
            result = load_sherlock_data(refresh=False)

        assert result == expected

    def test_does_not_call_network_when_cached(self, tmp_path: Path):
        """Cached path should not make any HTTP request."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        cache_file = data_dir / "sherlock.json"
        cache_file.write_text("{}", encoding="utf-8")

        mock_get = MagicMock()
        with patch("core.resources_loader._data_dir", return_value=data_dir), \
             patch("core.resources_loader.httpx.get", mock_get):
            load_sherlock_data(refresh=False)

        mock_get.assert_not_called()


# ---------------------------------------------------------------------------
# load_sherlock_data — download path
# ---------------------------------------------------------------------------

class TestLoadSherlockDownload:
    def test_downloads_when_no_cache(self, tmp_path: Path):
        """When cache doesn't exist, downloads from URL."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        expected = {"DownloadedSite": {"url": "http://dl/{}", "errorType": "status_code"}}
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = expected
        mock_resp.raise_for_status = MagicMock()

        with patch("core.resources_loader._data_dir", return_value=data_dir), \
             patch("core.resources_loader.httpx.get", return_value=mock_resp):
            result = load_sherlock_data(refresh=False)

        assert result == expected
        # Should have saved to cache
        cache_file = data_dir / "sherlock.json"
        assert cache_file.exists()

    def test_downloads_when_refresh(self, tmp_path: Path):
        """When refresh=True, downloads even if cache exists."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        cache_file = data_dir / "sherlock.json"
        cache_file.write_text('{"old": true}', encoding="utf-8")

        new_data = {"NewSite": {"url": "http://new/{}"}}
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = new_data
        mock_resp.raise_for_status = MagicMock()

        with patch("core.resources_loader._data_dir", return_value=data_dir), \
             patch("core.resources_loader.httpx.get", return_value=mock_resp):
            result = load_sherlock_data(refresh=True)

        assert result == new_data


# ---------------------------------------------------------------------------
# load_sherlock_data — download failure
# ---------------------------------------------------------------------------

class TestLoadSherlockDownloadFailure:
    def test_download_failure_raises(self, tmp_path: Path):
        """When download fails, exception should propagate (not silently empty)."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        import httpx
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server Error",
            request=MagicMock(),
            response=MagicMock(status_code=500),
        )

        with patch("core.resources_loader._data_dir", return_value=data_dir), \
             patch("core.resources_loader.httpx.get", return_value=mock_resp):
            with pytest.raises(httpx.HTTPStatusError):
                load_sherlock_data(refresh=False)


# ---------------------------------------------------------------------------
# get_default_list_path
# ---------------------------------------------------------------------------

class TestGetDefaultListPath:
    def test_returns_existing_file(self, tmp_path: Path):
        """When a file exists in the search path, returns it."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        test_file = data_dir / "username_sites.json"
        test_file.write_text("[]", encoding="utf-8")

        with patch("core.resources_loader._project_root", return_value=tmp_path), \
             patch("core.resources_loader.get_user_config_dir", return_value=tmp_path / "config"):
            result = get_default_list_path("username_sites.json")

        assert result is not None
        assert result.exists()

    def test_returns_none_when_missing(self, tmp_path: Path):
        """When no file exists, returns None."""
        with patch("core.resources_loader._project_root", return_value=tmp_path), \
             patch("core.resources_loader.get_user_config_dir", return_value=tmp_path / "config"):
            result = get_default_list_path("nonexistent_file.json")

        assert result is None
