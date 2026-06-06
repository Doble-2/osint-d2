"""Tests for HTTP client: proxy URL builder and client construction."""

from __future__ import annotations

from adapters.http_client import _build_proxy_url, build_async_client
from core.config import AppSettings


# ---------------------------------------------------------------------------
# _build_proxy_url
# ---------------------------------------------------------------------------

class TestBuildProxyUrl:
    def test_no_proxy_when_no_key(self):
        settings = AppSettings(proxy_api_key=None)
        assert _build_proxy_url(settings) is None

    def test_no_proxy_when_no_mode(self):
        settings = AppSettings(proxy_api_key="test-key", proxy_mode=None)
        # Auto-detect kicks in: key present → residential
        url = _build_proxy_url(settings)
        assert url is not None
        assert "residential" in url

    def test_residential_proxy(self):
        settings = AppSettings(
            proxy_api_key="my-api-key",
            proxy_mode="residential",
        )
        url = _build_proxy_url(settings)
        assert url == "http://scrapingant:my-api-key@residential.scrapingant.com:8080"

    def test_datacenter_proxy(self):
        settings = AppSettings(
            proxy_api_key="my-api-key",
            proxy_mode="datacenter",
        )
        url = _build_proxy_url(settings)
        assert url == "http://scrapingant:my-api-key@datacenter.scrapingant.com:8080"

    def test_residential_with_country(self):
        settings = AppSettings(
            proxy_api_key="key123",
            proxy_mode="residential",
            proxy_country="us",
        )
        url = _build_proxy_url(settings)
        assert "proxy_country=us" in url
        assert "key123" in url

    def test_unknown_mode_returns_none(self):
        settings = AppSettings(
            proxy_api_key="key",
            proxy_mode="unknown_mode",
        )
        assert _build_proxy_url(settings) is None

    def test_empty_key_returns_none(self):
        settings = AppSettings(proxy_api_key="", proxy_mode="residential")
        assert _build_proxy_url(settings) is None


# ---------------------------------------------------------------------------
# build_async_client
# ---------------------------------------------------------------------------

class TestBuildAsyncClient:
    def test_client_without_proxy(self):
        settings = AppSettings(proxy_api_key=None)
        client = build_async_client(settings)
        assert client is not None
        # No proxy configured.
        assert client._transport is not None

    def test_client_with_proxy(self):
        settings = AppSettings(
            proxy_api_key="test-key",
            proxy_mode="residential",
        )
        client = build_async_client(settings)
        assert client is not None


# ---------------------------------------------------------------------------
# effective_proxy_mode
# ---------------------------------------------------------------------------

class TestEffectiveProxyMode:
    def test_auto_detect_from_key(self):
        settings = AppSettings(proxy_api_key="some-key")
        assert settings.effective_proxy_mode == "residential"

    def test_explicit_mode_overrides(self):
        settings = AppSettings(proxy_api_key="key", proxy_mode="datacenter")
        assert settings.effective_proxy_mode == "datacenter"

    def test_no_key_no_mode(self):
        settings = AppSettings(proxy_api_key=None, proxy_mode=None)
        assert settings.effective_proxy_mode is None
