"""Tests para el módulo de rate limiting por dominio."""

from __future__ import annotations

import asyncio
import time

import httpx
import pytest

from adapters.rate_limiter import (
    DomainRateLimiter,
    extract_domain,
    parse_retry_after,
    request_with_retry,
)


# ---------------------------------------------------------------------------
# extract_domain
# ---------------------------------------------------------------------------

class TestExtractDomain:
    def test_simple_url(self):
        assert extract_domain("https://github.com/user123") == "github.com"

    def test_with_port(self):
        assert extract_domain("http://localhost:8080/path") == "localhost"

    def test_subdomain(self):
        assert extract_domain("https://api.github.com/users/test") == "api.github.com"

    def test_no_scheme(self):
        # urlparse sin scheme no da hostname
        result = extract_domain("github.com/user")
        assert isinstance(result, str)

    def test_empty_string(self):
        assert extract_domain("") == "unknown"

    def test_invalid_url(self):
        assert isinstance(extract_domain("not-a-url"), str)


# ---------------------------------------------------------------------------
# parse_retry_after
# ---------------------------------------------------------------------------

class TestParseRetryAfter:
    def test_none_header(self):
        assert parse_retry_after(None) is None

    def test_empty_header(self):
        assert parse_retry_after("") is None

    def test_seconds_integer(self):
        result = parse_retry_after("30")
        assert result == 30.0

    def test_seconds_float(self):
        result = parse_retry_after("1.5")
        assert result == 1.5

    def test_seconds_zero(self):
        result = parse_retry_after("0")
        assert result == 0.0

    def test_negative_seconds(self):
        assert parse_retry_after("-5") is None

    def test_cap_at_120_seconds(self):
        result = parse_retry_after("300")
        assert result == 120.0

    def test_http_date_format(self):
        # HTTP-date lejano
        result = parse_retry_after("Thu, 01 Jan 2099 00:00:00 GMT")
        assert result is not None
        assert result > 0

    def test_unparseable(self):
        assert parse_retry_after("not-a-date-or-number") is None


# ---------------------------------------------------------------------------
# DomainRateLimiter — basic
# ---------------------------------------------------------------------------

class TestDomainRateLimiter:
    def test_default_construction(self):
        rl = DomainRateLimiter()
        assert rl.retry_max_attempts == 3

    def test_custom_params(self):
        rl = DomainRateLimiter(
            per_domain_concurrency=5,
            delay_ms=500,
            jitter_ms=50,
            retry_max_attempts=2,
        )
        assert rl.retry_max_attempts == 2
        assert rl._per_domain_concurrency == 5

    def test_should_retry_429(self):
        assert DomainRateLimiter.should_retry(429) is True

    def test_should_retry_503(self):
        assert DomainRateLimiter.should_retry(503) is True

    def test_should_not_retry_200(self):
        assert DomainRateLimiter.should_retry(200) is False

    def test_should_not_retry_404(self):
        assert DomainRateLimiter.should_retry(404) is False

    def test_should_not_retry_500(self):
        assert DomainRateLimiter.should_retry(500) is False

    def test_backoff_delay_without_retry_after(self):
        d0 = DomainRateLimiter.backoff_delay(0)
        d1 = DomainRateLimiter.backoff_delay(1)
        d2 = DomainRateLimiter.backoff_delay(2)
        # Exponential: 1s, 2s, 4s (+ jitter)
        assert 0.5 < d0 < 2.0
        assert 1.5 < d1 < 3.0
        assert 3.5 < d2 < 5.0

    def test_backoff_delay_with_retry_after(self):
        d = DomainRateLimiter.backoff_delay(0, retry_after=10.0)
        # Should use Retry-After as base + small jitter
        assert 10.0 < d < 11.0


# ---------------------------------------------------------------------------
# DomainRateLimiter — throttle context manager
# ---------------------------------------------------------------------------

class TestDomainRateLimiterThrottle:
    @pytest.mark.asyncio
    async def test_throttle_acquires_and_releases(self):
        rl = DomainRateLimiter(delay_ms=0, jitter_ms=0, per_domain_concurrency=2)
        async with rl.throttle("https://example.com/page1"):
            # Inside: one slot taken
            pass
        # After: slot released

    @pytest.mark.asyncio
    async def test_per_domain_concurrency_limits(self):
        """Verifica que per_domain_concurrency=1 serializa requests al mismo dominio."""
        rl = DomainRateLimiter(
            delay_ms=0, jitter_ms=0,
            per_domain_concurrency=1,
        )

        order: list[str] = []

        async def task(label: str, url: str):
            async with rl.throttle(url):
                order.append(f"{label}_start")
                await asyncio.sleep(0.05)
                order.append(f"{label}_end")

        # Mismo dominio → serializado
        await asyncio.gather(
            task("a", "https://example.com/1"),
            task("b", "https://example.com/2"),
        )
        # Con concurrency=1, uno debe terminar antes de que otro empiece
        a_end = order.index("a_end")
        b_start = order.index("b_start")
        b_end = order.index("b_end")
        a_start = order.index("a_start")
        # Uno de los dos patrones: a termina antes de b empieza, o viceversa
        assert (a_end < b_start) or (b_end < a_start)

    @pytest.mark.asyncio
    async def test_different_domains_not_blocked(self):
        """Requests a diferentes dominios no se bloquean entre sí."""
        rl = DomainRateLimiter(
            delay_ms=0, jitter_ms=0,
            per_domain_concurrency=1,
        )

        results: list[float] = []

        async def task(url: str):
            async with rl.throttle(url):
                results.append(time.monotonic())
                await asyncio.sleep(0.05)


        await asyncio.gather(
            task("https://example.com/page"),
            task("https://other.com/page"),
        )
        # Ambos deberían empezar casi simultáneamente (< 30ms gap)
        assert len(results) == 2
        assert abs(results[0] - results[1]) < 0.03

    @pytest.mark.asyncio
    async def test_delay_enforced_between_requests(self):
        """Verifica que se respeta el delay entre requests al mismo dominio."""
        rl = DomainRateLimiter(
            delay_ms=100, jitter_ms=0,
            per_domain_concurrency=10,  # alto para no bloquear por semáforo
        )

        times: list[float] = []

        async def task(url: str):
            async with rl.throttle(url):
                times.append(time.monotonic())

        # Requests secuenciales al mismo dominio
        await task("https://example.com/1")
        await task("https://example.com/2")

        assert len(times) == 2
        gap = times[1] - times[0]
        # Debe haber al menos ~100ms de gap
        assert gap >= 0.08  # Pequeño margen por timing del OS


# ---------------------------------------------------------------------------
# request_with_retry
# ---------------------------------------------------------------------------

class TestRequestWithRetry:
    @pytest.mark.asyncio
    async def test_success_no_retry(self):
        """Request exitoso no reintenta."""
        rl = DomainRateLimiter(delay_ms=0, jitter_ms=0, retry_max_attempts=3)

        mock_response = httpx.Response(
            200,
            request=httpx.Request("GET", "https://example.com"),
            text="OK",
        )

        call_count = 0

        class MockClient:
            async def get(self, url, headers=None):
                nonlocal call_count
                call_count += 1
                return mock_response

            async def head(self, url, headers=None):
                return mock_response

            async def post(self, url, content=None, headers=None):
                return mock_response

        client = MockClient()
        resp = await request_with_retry(client, "GET", "https://example.com", rl)
        assert resp.status_code == 200
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retry_on_429(self):
        """Reintenta en 429 hasta éxito."""
        rl = DomainRateLimiter(delay_ms=0, jitter_ms=0, retry_max_attempts=3)

        responses = [
            httpx.Response(
                429,
                request=httpx.Request("GET", "https://example.com"),
                headers={"Retry-After": "0"},
            ),
            httpx.Response(
                200,
                request=httpx.Request("GET", "https://example.com"),
                text="OK",
            ),
        ]
        call_count = 0

        class MockClient:
            async def get(self, url, headers=None):
                nonlocal call_count
                resp = responses[min(call_count, len(responses) - 1)]
                call_count += 1
                return resp

            async def head(self, url, headers=None):
                return responses[-1]

            async def post(self, url, content=None, headers=None):
                return responses[-1]

        client = MockClient()
        resp = await request_with_retry(client, "GET", "https://example.com", rl)
        assert resp.status_code == 200
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_retry_exhausted_returns_last(self):
        """Si se agotan los reintentos, devuelve la última respuesta 429."""
        rl = DomainRateLimiter(delay_ms=0, jitter_ms=0, retry_max_attempts=2)

        error_resp = httpx.Response(
            429,
            request=httpx.Request("GET", "https://example.com"),
            headers={"Retry-After": "0"},
        )

        call_count = 0

        class MockClient:
            async def get(self, url, headers=None):
                nonlocal call_count
                call_count += 1
                return error_resp

            async def head(self, url, headers=None):
                return error_resp

            async def post(self, url, content=None, headers=None):
                return error_resp

        client = MockClient()
        resp = await request_with_retry(client, "GET", "https://example.com", rl)
        assert resp.status_code == 429
        # 1 initial + 2 retries = 3
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_no_retry_on_404(self):
        """No reintenta en 404."""
        rl = DomainRateLimiter(delay_ms=0, jitter_ms=0, retry_max_attempts=3)

        mock_response = httpx.Response(
            404,
            request=httpx.Request("GET", "https://example.com"),
        )

        call_count = 0

        class MockClient:
            async def get(self, url, headers=None):
                nonlocal call_count
                call_count += 1
                return mock_response

            async def head(self, url, headers=None):
                return mock_response

            async def post(self, url, content=None, headers=None):
                return mock_response

        client = MockClient()
        resp = await request_with_retry(client, "GET", "https://example.com", rl)
        assert resp.status_code == 404
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retry_on_503(self):
        """Reintenta en 503."""
        rl = DomainRateLimiter(delay_ms=0, jitter_ms=0, retry_max_attempts=1)

        responses = [
            httpx.Response(503, request=httpx.Request("GET", "https://example.com")),
            httpx.Response(200, request=httpx.Request("GET", "https://example.com"), text="OK"),
        ]
        call_count = 0

        class MockClient:
            async def get(self, url, headers=None):
                nonlocal call_count
                resp = responses[min(call_count, len(responses) - 1)]
                call_count += 1
                return resp

            async def head(self, url, headers=None):
                return responses[-1]

            async def post(self, url, content=None, headers=None):
                return responses[-1]

        client = MockClient()
        resp = await request_with_retry(client, "GET", "https://example.com", rl)
        assert resp.status_code == 200
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_zero_retries_no_retry(self):
        """Con retry_max_attempts=0, no reintenta."""
        rl = DomainRateLimiter(delay_ms=0, jitter_ms=0, retry_max_attempts=0)

        error_resp = httpx.Response(
            429,
            request=httpx.Request("GET", "https://example.com"),
        )

        call_count = 0

        class MockClient:
            async def get(self, url, headers=None):
                nonlocal call_count
                call_count += 1
                return error_resp

            async def head(self, url, headers=None):
                return error_resp

            async def post(self, url, content=None, headers=None):
                return error_resp

        client = MockClient()
        resp = await request_with_retry(client, "GET", "https://example.com", rl)
        assert resp.status_code == 429
        assert call_count == 1


# ---------------------------------------------------------------------------
# Config integration
# ---------------------------------------------------------------------------

class TestConfigIntegration:
    def test_new_config_fields_defaults(self):
        from core.config import AppSettings
        s = AppSettings()
        assert s.request_delay_ms == 200
        assert s.request_jitter_ms == 100
        assert s.per_domain_concurrency == 3
        assert s.retry_max_attempts == 3

    def test_max_concurrency_cap(self):
        from core.config import AppSettings
        # 50 debería ser el máximo
        s = AppSettings(sites_max_concurrency=50)
        assert s.sites_max_concurrency == 50

    def test_max_concurrency_over_cap_fails(self):
        from core.config import AppSettings
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            AppSettings(sites_max_concurrency=500)
