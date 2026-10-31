"""Tests for the official Have I Been Pwned API client."""

from __future__ import annotations

import httpx
import pytest

from adapters import breach_check
from adapters.breach_check import enrich_profiles_with_breach_data
from core.config import AppSettings

BREACH = {"Name": "Demo", "Title": "Demo", "Domain": "example.com", "BreachDate": "2020-01-01", "AddedDate": "2020-02-01T00:00:00Z", "ModifiedDate": "2020-02-01T00:00:00Z", "PwnCount": 10, "Description": "Demo breach", "DataClasses": ["Emails"], "IsVerified": True, "IsFabricated": False, "IsSensitive": False, "IsRetired": False, "IsSpamList": False, "IsMalware": False, "IsSubscriptionFree": False, "LogoPath": "https://example.com/logo.png"}


def _settings(key: str | None = "test-key") -> AppSettings:
    return AppSettings(hibp_api_key=key)


@pytest.fixture
def mock_api(monkeypatch):
    real_client = httpx.Client

    def install(handler):
        monkeypatch.setattr(
            breach_check.httpx,
            "Client",
            lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
        )

    return install


def test_uses_official_api_with_key_and_encoded_email(mock_api):
    seen = {}

    def handler(request):
        seen.update(url=str(request.url), key=request.headers["hibp-api-key"], agent=request.headers["user-agent"])
        return httpx.Response(200, json=[BREACH])

    mock_api(handler)
    [profile] = enrich_profiles_with_breach_data(["a+b@example.com"], settings=_settings())

    assert seen["url"] == "https://haveibeenpwned.com/api/v3/breachedaccount/a%2Bb%40example.com?truncateResponse=false"
    assert seen["key"] == "test-key"
    assert "Chrome" not in seen["agent"]
    assert profile.exists is True
    assert profile.metadata["breach_count"] == 1
    assert profile.metadata["breaches"]["breaches"][0]["title"] == "Demo"


def test_404_means_no_breaches(mock_api):
    mock_api(lambda request: httpx.Response(404))
    [profile] = enrich_profiles_with_breach_data(["a@example.com"], settings=_settings())

    assert profile.exists is True
    assert profile.metadata["breach_count"] == 0


def test_missing_key_makes_no_request(mock_api):
    def handler(request):
        raise AssertionError("no request expected without a key")

    mock_api(handler)
    [profile] = enrich_profiles_with_breach_data(["a@example.com"], settings=_settings(None))

    assert profile.exists is False
    assert profile.metadata["error"] == "hibp_api_key_missing"


@pytest.mark.parametrize("status", [401, 429, 503])
def test_api_errors_are_reported(mock_api, status):
    mock_api(lambda request: httpx.Response(status))
    [profile] = enrich_profiles_with_breach_data(["a@example.com"], settings=_settings())

    assert profile.exists is False
    assert profile.metadata["error"] == f"hibp_http_{status}"


def test_network_failure_is_reported_not_dropped(mock_api):
    def handler(request):
        raise httpx.ConnectError("down")

    mock_api(handler)
    [profile] = enrich_profiles_with_breach_data(["a@example.com"], settings=_settings())

    assert profile.metadata["error"] == "hibp_request_failed"
