"""Tests for the SSRF guard (issue #25).

Covers:
- Blocked IMDS endpoints (AWS, GCP, Azure)
- Private IP ranges (RFC 1918, loopback, link-local)
- IPv6 private ranges
- DNS rebinding to private IPs
- Valid public URLs pass through
- Integration with fetch_url in execute_tool
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.services.url_guard import SSRFBlockedError, validate_url


# ---------------------------------------------------------------------------
# Direct validate_url tests
# ---------------------------------------------------------------------------


class TestBlockedIMDSEndpoints:
    """IMDS endpoints must be blocked regardless of path."""

    def test_aws_imds(self):
        with pytest.raises(SSRFBlockedError, match="169.254.169.254"):
            validate_url("http://169.254.169.254/latest/meta-data/")

    def test_aws_imds_credentials(self):
        with pytest.raises(SSRFBlockedError):
            validate_url(
                "http://169.254.169.254/latest/meta-data/iam/security-credentials/my-role"
            )

    def test_gcp_metadata(self):
        with pytest.raises(SSRFBlockedError, match="metadata.google.internal"):
            validate_url(
                "http://metadata.google.internal/computeMetadata/v1/"
            )

    def test_gcp_metadata_alt(self):
        with pytest.raises(SSRFBlockedError, match="metadata.goog"):
            validate_url("http://metadata.goog/computeMetadata/v1/")

    def test_azure_metadata(self):
        with pytest.raises(SSRFBlockedError):
            validate_url(
                "http://169.254.169.254/metadata/instance?api-version=2021-02-01"
            )


class TestBlockedPrivateIPs:
    """Private RFC 1918 and other reserved ranges must be blocked."""

    @pytest.mark.parametrize(
        "url",
        [
            "http://10.0.0.1/",
            "http://10.255.255.255/",
            "http://172.16.0.1/",
            "http://172.31.255.255/",
            "http://192.168.0.1/",
            "http://192.168.1.100:8080/admin",
        ],
    )
    def test_rfc1918_blocked(self, url: str):
        with pytest.raises(SSRFBlockedError):
            validate_url(url)

    def test_loopback_ip(self):
        with pytest.raises(SSRFBlockedError):
            validate_url("http://127.0.0.1:9200/")

    def test_loopback_range(self):
        with pytest.raises(SSRFBlockedError):
            validate_url("http://127.0.0.2/")

    def test_link_local(self):
        with pytest.raises(SSRFBlockedError):
            validate_url("http://169.254.1.1/")

    def test_zero_network(self):
        with pytest.raises(SSRFBlockedError):
            validate_url("http://0.0.0.0/")

    def test_carrier_grade_nat(self):
        with pytest.raises(SSRFBlockedError):
            validate_url("http://100.64.0.1/")


class TestBlockedHostnames:
    """Known internal hostnames must be blocked."""

    def test_localhost(self):
        with pytest.raises(SSRFBlockedError, match="localhost"):
            validate_url("http://localhost:5432/")

    def test_localhost_https(self):
        with pytest.raises(SSRFBlockedError):
            validate_url("https://localhost/admin")

    def test_zero_host(self):
        with pytest.raises(SSRFBlockedError):
            validate_url("http://0.0.0.0:8080/")


class TestBlockedIPv6:
    """IPv6 private/reserved ranges must be blocked."""

    def test_ipv6_loopback(self):
        with pytest.raises(SSRFBlockedError):
            validate_url("http://[::1]/")

    def test_ipv6_unique_local(self):
        with pytest.raises(SSRFBlockedError):
            validate_url("http://[fd00::1]/")

    def test_ipv6_link_local(self):
        with pytest.raises(SSRFBlockedError):
            validate_url("http://[fe80::1]/")


class TestDNSRebinding:
    """Hostnames that resolve to private IPs must be blocked."""

    def test_hostname_resolving_to_loopback(self):
        fake_result = [
            (2, 1, 6, "", ("127.0.0.1", 0)),
        ]
        with patch("core.services.url_guard.socket.getaddrinfo", return_value=fake_result):
            with pytest.raises(SSRFBlockedError, match="resolves to a private"):
                validate_url("http://evil-rebind.attacker.com/steal")

    def test_hostname_resolving_to_internal(self):
        fake_result = [
            (2, 1, 6, "", ("10.0.0.5", 0)),
        ]
        with patch("core.services.url_guard.socket.getaddrinfo", return_value=fake_result):
            with pytest.raises(SSRFBlockedError):
                validate_url("http://corporate-proxy.example.com/")


class TestValidPublicURLs:
    """Legitimate public URLs must pass validation."""

    @pytest.mark.parametrize(
        "url",
        [
            "https://github.com/user",
            "https://example.com/portfolio",
            "http://blog.example.org/about",
            "https://1.1.1.1/dns-query",
            "https://8.8.8.8/",
        ],
    )
    def test_public_url_passes(self, url: str):
        # Patch DNS resolution to return a public IP
        fake_result = [(2, 1, 6, "", ("93.184.216.34", 0))]
        with patch("core.services.url_guard.socket.getaddrinfo", return_value=fake_result):
            result = validate_url(url)
            assert result == url


class TestMalformedURLs:
    """Malformed or invalid URLs raise ValueError."""

    def test_no_scheme(self):
        with pytest.raises(ValueError, match="scheme"):
            validate_url("ftp://internal.corp/data")

    def test_empty_host(self):
        with pytest.raises(ValueError, match="hostname"):
            validate_url("http:///path")


# ---------------------------------------------------------------------------
# Integration: execute_tool fetch_url with SSRF guard
# ---------------------------------------------------------------------------


class TestFetchUrlSSRFIntegration:
    """Verify that execute_tool('fetch_url', ...) blocks SSRF attempts."""

    @pytest.mark.asyncio
    async def test_imds_blocked_in_execute_tool(self):
        from core.config import AppSettings
        from core.services.agent_tools import execute_tool

        result = await execute_tool(
            "fetch_url",
            {"url": "http://169.254.169.254/latest/meta-data/"},
            settings=AppSettings(),
        )
        data = json.loads(result)
        assert "error" in data
        assert "SSRF blocked" in data["error"]

    @pytest.mark.asyncio
    async def test_localhost_blocked_in_execute_tool(self):
        from core.config import AppSettings
        from core.services.agent_tools import execute_tool

        result = await execute_tool(
            "fetch_url",
            {"url": "http://localhost:9200/_cat/indices"},
            settings=AppSettings(),
        )
        data = json.loads(result)
        assert "error" in data
        assert "SSRF blocked" in data["error"]

    @pytest.mark.asyncio
    async def test_internal_ip_blocked_in_execute_tool(self):
        from core.config import AppSettings
        from core.services.agent_tools import execute_tool

        result = await execute_tool(
            "fetch_url",
            {"url": "http://10.0.0.1/admin"},
            settings=AppSettings(),
        )
        data = json.loads(result)
        assert "error" in data
        assert "SSRF blocked" in data["error"]

    @pytest.mark.asyncio
    async def test_public_url_still_works(self):
        """A legitimate public URL should pass the guard and reach httpx."""
        import httpx
        from contextlib import asynccontextmanager
        from core.config import AppSettings
        from core.services.agent_tools import execute_tool

        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 200
        resp.text = "<html><head><title>Portfolio</title></head><body></body></html>"
        resp.url = httpx.URL("https://example.com/portfolio")

        @asynccontextmanager
        async def mock_client_cm(*args, **kwargs):
            client = AsyncMock()
            client.get = AsyncMock(return_value=resp)
            yield client

        # Patch DNS to return a public IP so the guard passes
        fake_dns = [(2, 1, 6, "", ("93.184.216.34", 0))]
        with patch("core.services.url_guard.socket.getaddrinfo", return_value=fake_dns), \
             patch("adapters.http_client.build_async_client", mock_client_cm):
            result = await execute_tool(
                "fetch_url",
                {"url": "https://example.com/portfolio"},
                settings=AppSettings(),
            )

        data = json.loads(result)
        assert "error" not in data
        assert data["status_code"] == 200
