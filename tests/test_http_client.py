"""Tests for HTTP client: proxy URL builder and client construction."""

from __future__ import annotations

from adapters.http_client import _build_proxy_url, build_async_client
from core.config import AppSettings


# ---------------------------------------------------------------------------
# _build_proxy_url — standalone proxy (with username)
# ---------------------------------------------------------------------------

class TestBuildProxyUrlStandalone:
    def test_residential_with_username(self):
        settings = AppSettings(
            proxy_api_key="my-password",
            proxy_username="angeldOzt2u",
            proxy_mode="residential",
        )
        base_url, auth = _build_proxy_url(settings)
        assert base_url == "http://residential.scrapingant.com:8080"
        assert auth == ("customer-angeldOzt2u", "my-password")
        # Key must NOT appear in the URL
        assert "my-password" not in base_url

    def test_datacenter_with_username(self):
        settings = AppSettings(
            proxy_api_key="my-password",
            proxy_username="angeldOzt2u",
            proxy_mode="datacenter",
        )
        base_url, auth = _build_proxy_url(settings)
        assert base_url == "http://datacenter.scrapingant.com:8080"
        assert auth == ("customer-angeldOzt2u", "my-password")
        assert "my-password" not in base_url

    def test_residential_with_country(self):
        settings = AppSettings(
            proxy_api_key="key123",
            proxy_username="myuser",
            proxy_mode="residential",
            proxy_country="us",
        )
        base_url, auth = _build_proxy_url(settings)
        assert base_url == "http://residential.scrapingant.com:8080"
        assert auth == ("customer-myuser-country-us", "key123")
        assert "key123" not in base_url


# ---------------------------------------------------------------------------
# _build_proxy_url — API Proxy Mode (no username)
# ---------------------------------------------------------------------------

class TestBuildProxyUrlApiMode:
    def test_api_mode_residential(self):
        settings = AppSettings(
            proxy_api_key="my-api-key",
            proxy_username=None,
            proxy_mode="residential",
        )
        base_url, auth = _build_proxy_url(settings)
        assert base_url == "http://proxy.scrapingant.com:8080"
        assert auth is not None
        username, password = auth
        assert "scrapingant" in username
        assert "proxy_type=residential" in username
        assert password == "my-api-key"
        # Key must NOT appear in the URL
        assert "my-api-key" not in base_url

    def test_api_mode_with_country(self):
        settings = AppSettings(
            proxy_api_key="key",
            proxy_username=None,
            proxy_mode="residential",
            proxy_country="de",
        )
        base_url, auth = _build_proxy_url(settings)
        assert "proxy.scrapingant.com" in base_url
        username, _ = auth
        assert "proxy_country=de" in username
        assert "key" not in base_url


# ---------------------------------------------------------------------------
# _build_proxy_url — edge cases
# ---------------------------------------------------------------------------

class TestBuildProxyUrlEdgeCases:
    def test_no_proxy_when_no_key(self):
        settings = AppSettings(proxy_api_key=None)
        base_url, auth = _build_proxy_url(settings)
        assert base_url is None
        assert auth is None

    def test_auto_detect_mode_from_key(self):
        settings = AppSettings(proxy_api_key="test-key", proxy_mode=None)
        base_url, auth = _build_proxy_url(settings)
        assert base_url is not None
        assert auth is not None
        # Auto-detected mode is "residential" — visible in the auth username
        assert "residential" in auth[0]

    def test_unknown_mode_returns_none(self):
        settings = AppSettings(
            proxy_api_key="key",
            proxy_mode="unknown_mode",
        )
        base_url, auth = _build_proxy_url(settings)
        assert base_url is None
        assert auth is None

    def test_empty_key_returns_none(self):
        settings = AppSettings(proxy_api_key="", proxy_mode="residential")
        base_url, auth = _build_proxy_url(settings)
        assert base_url is None
        assert auth is None


# ---------------------------------------------------------------------------
# build_async_client
# ---------------------------------------------------------------------------

class TestBuildAsyncClient:
    def test_client_without_proxy(self):
        settings = AppSettings(proxy_api_key=None)
        client = build_async_client(settings)
        assert client is not None
        assert client._transport is not None

    def test_client_with_proxy(self):
        settings = AppSettings(
            proxy_api_key="test-key",
            proxy_username="testuser",
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


# ---------------------------------------------------------------------------
# SecretStr redaction (issue #27)
# ---------------------------------------------------------------------------

class TestSecretStrRedaction:
    def test_model_dump_does_not_expose_proxy_key(self):
        settings = AppSettings(proxy_api_key="super-secret-key-12345")
        dumped = settings.model_dump()
        # SecretStr serializes as '**********' in model_dump
        assert dumped["proxy_api_key"] != "super-secret-key-12345"
        assert "super-secret" not in str(dumped["proxy_api_key"])

    def test_model_dump_does_not_expose_ai_key(self):
        settings = AppSettings(ai_api_key="sk-my-secret-ai-key")
        dumped = settings.model_dump()
        assert dumped["ai_api_key"] != "sk-my-secret-ai-key"
        assert "sk-my-secret" not in str(dumped["ai_api_key"])

    def test_proxy_url_does_not_contain_key(self):
        settings = AppSettings(
            proxy_api_key="LIVE_SECRET_KEY",
            proxy_username="user1",
            proxy_mode="residential",
        )
        base_url, auth = _build_proxy_url(settings)
        assert "LIVE_SECRET_KEY" not in base_url
        assert auth[1] == "LIVE_SECRET_KEY"

    def test_secret_value_accessible_via_getter(self):
        settings = AppSettings(proxy_api_key="my-key-value")
        assert settings.proxy_api_key.get_secret_value() == "my-key-value"

    def test_repr_does_not_expose_key(self):
        settings = AppSettings(proxy_api_key="secret123", ai_api_key="sk-secret")
        repr_str = repr(settings)
        assert "secret123" not in repr_str
        assert "sk-secret" not in repr_str
