# Adding a Scanner

This guide adds a username source. The example works in the real pipeline, and `tests/test_scanner_contract.py` checks it against every registered scanner.

A scanner is a class in `src/adapters/osint_sources/` that implements the `OSINTScanner` protocol from `src/core/interfaces/scanner.py`:

```python
class OSINTScanner(Protocol):
    async def scan(self, username: str) -> SocialProfile: ...
```

Email sources use the same method, and receive the email address as the argument.

## 1. Create the scanner

```python
# src/adapters/osint_sources/newplatform.py
"""Scanner for NewPlatform public profiles."""

from __future__ import annotations

from adapters.http_client import build_async_client
from core.config import AppSettings
from core.domain.models import SocialProfile
from core.interfaces.scanner import OSINTScanner


class NewPlatformScanner(OSINTScanner):
    _base_url = "https://newplatform.example"

    def __init__(self, settings: AppSettings | None = None) -> None:
        self._settings = settings or AppSettings()

    async def scan(self, username: str) -> SocialProfile:
        url = f"{self._base_url}/{username}"

        async with build_async_client(self._settings) as client:
            response = await client.get(url)

        return SocialProfile(
            url=str(response.url),
            username=username,
            network_name="newplatform",
            exists=response.status_code == 200,
            metadata={"status_code": response.status_code},
        )
```

Rules:

- **Always return a `SocialProfile`.** Use `exists=False` when the profile does not exist.
- **Use `build_async_client`,** so timeouts and proxy settings apply.
- **Let network exceptions propagate.** The pipeline records them as an error on that source, so one failure doesn't stop the scan.
- **Keep the constructor callable with no arguments.** The pipeline creates each scanner with `scanner()`.

## 2. Register it

Add the class to `_USERNAME_SCANNERS` in `src/core/services/identity_pipeline.py`, or `_EMAIL_SCANNERS` for an email source:

```python
from adapters.osint_sources.newplatform import NewPlatformScanner

_USERNAME_SCANNERS = (
    # ...existing scanners...
    NewPlatformScanner,
)
```

## 3. Add a test

```python
# tests/test_newplatform_scanner.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adapters.osint_sources.newplatform import NewPlatformScanner


@pytest.mark.asyncio
@pytest.mark.parametrize(("status", "exists"), [(200, True), (404, False)])
async def test_scan(status, exists):
    response = MagicMock(status_code=status, url="https://newplatform.example/demo")
    client = AsyncMock()
    client.get.return_value = response
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=client)
    context.__aexit__ = AsyncMock(return_value=False)

    with patch("adapters.osint_sources.newplatform.build_async_client", return_value=context):
        profile = await NewPlatformScanner().scan("demo")

    assert profile.exists is exists
    assert profile.network_name == "newplatform"
```

## 4. Verify

```bash
poetry run pytest tests/test_newplatform_scanner.py tests/test_scanner_contract.py
poetry run pytest
poetry run ruff check .
```

## Tips

- Put platform-specific data in `metadata`. The keys `name`, `location`, `company`, `email`, and `followers` reach the agent; see `_compact_profiles` in `agent_tools.py`.
- Fill in `bio` and `image_url` when available. They are used for correlation and the dossier.
- Respect the platform's terms of service and rate limits.
