"""Fake for ``httpx.AsyncClient.stream``, the call behind ``get_limited``."""

from __future__ import annotations

from contextlib import asynccontextmanager

import httpx


def stream_of(*responses):
    """Return a ``client.stream`` that answers with *responses*, in order."""
    queue = list(responses)

    @asynccontextmanager
    async def stream(method, url, **kwargs):
        stream.calls += 1
        item = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(item, Exception):
            raise item
        text = getattr(item, "text", None)
        text = text if isinstance(text, str) else ""
        headers = getattr(item, "headers", None)
        headers = headers if isinstance(headers, dict) else {}
        final_url = str(getattr(item, "url", url))
        yield httpx.Response(item.status_code, headers=headers, text=text, request=httpx.Request(method, final_url))

    stream.calls = 0
    return stream
