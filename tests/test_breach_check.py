"""Tests for breach_check module: header generation and HIBP enrichment."""

from __future__ import annotations

from adapters.breach_check import _build_hibp_headers


class TestBuildHibpHeaders:
    def test_headers_have_required_keys(self):
        h = _build_hibp_headers()
        required = {"accept", "referer", "request-id", "traceparent", "user-agent"}
        assert required.issubset(h.keys())

    def test_headers_are_unique_per_call(self):
        h1 = _build_hibp_headers()
        h2 = _build_hibp_headers()
        assert h1["request-id"] != h2["request-id"]
        assert h1["traceparent"] != h2["traceparent"]

    def test_traceparent_format(self):
        h = _build_hibp_headers()
        parts = h["traceparent"].split("-")
        assert len(parts) == 4
        assert parts[0] == "00"
        assert parts[3] == "01"
        assert len(parts[1]) == 32  # trace_id hex
        assert len(parts[2]) == 16  # span_id hex

    def test_request_id_format(self):
        h = _build_hibp_headers()
        rid = h["request-id"]
        assert rid.startswith("|")
        assert "." in rid
