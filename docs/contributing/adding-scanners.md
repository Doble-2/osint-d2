# Adding a Scanner

Step-by-step guide to adding a new OSINT data source to OSINT-D2.

## Overview

OSINT-D2 scanners follow Clean Architecture: each scanner is an **adapter** that implements the `OSINTScanner` protocol. The core pipeline discovers and invokes scanners automatically.

## Step 1: Create the Scanner

Create a new file in `src/adapters/osint_sources/`:

```python
# src/adapters/osint_sources/newplatform.py
"""NewPlatform scanner — discovers user profiles via their public API."""

from __future__ import annotations

import httpx

from core.domain.models import SocialProfile
from core.interfaces.scanner import OSINTScanner


class NewPlatformScanner(OSINTScanner):
    """Scans NewPlatform for a username."""

    PLATFORM = "newplatform"

    async def scan_username(
        self,
        username: str,
        client: httpx.AsyncClient,
    ) -> SocialProfile | None:
        """Check if the username exists on NewPlatform."""
        url = f"https://api.newplatform.com/users/{username}"

        try:
            resp = await client.get(url)
            if resp.status_code == 404:
                return SocialProfile(
                    url=url,
                    username=username,
                    network_name=self.PLATFORM,
                    exists=False,
                )

            data = resp.json()
            return SocialProfile(
                url=f"https://newplatform.com/{username}",
                username=username,
                network_name=self.PLATFORM,
                exists=True,
                bio=data.get("bio"),
                image_url=data.get("avatar_url"),
                metadata={
                    "source": "newplatform_api",
                    "followers": data.get("followers_count"),
                    "created_at": data.get("created_at"),
                },
            )
        except Exception:
            return None
```

## Step 2: Implement the Protocol

Your scanner must match the `OSINTScanner` protocol defined in `src/core/interfaces/scanner.py`:

```python
class OSINTScanner(Protocol):
    PLATFORM: str

    async def scan_username(
        self,
        username: str,
        client: httpx.AsyncClient,
    ) -> SocialProfile | None: ...
```

Key rules:

- Return `SocialProfile(exists=True, ...)` when the profile is found
- Return `SocialProfile(exists=False, ...)` when confirmed not found
- Return `None` on network errors (the pipeline handles retries)
- Never raise exceptions — catch and return `None`

## Step 3: Register in the Pipeline

Add your scanner to `src/core/services/identity_pipeline.py`:

```python
from adapters.osint_sources.newplatform import NewPlatformScanner

_USERNAME_SCANNERS = (
    # ... existing scanners ...
    NewPlatformScanner,
)
```

## Step 4: Add a Test

Create `tests/test_newplatform_scanner.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock

from adapters.osint_sources.newplatform import NewPlatformScanner


class TestNewPlatformScanner:
    @pytest.mark.asyncio
    async def test_found_profile(self):
        scanner = NewPlatformScanner()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "bio": "Developer",
            "followers_count": 100,
        }

        client = AsyncMock()
        client.get.return_value = mock_resp

        result = await scanner.scan_username("testuser", client)
        assert result is not None
        assert result.exists is True
        assert result.network_name == "newplatform"

    @pytest.mark.asyncio
    async def test_not_found(self):
        scanner = NewPlatformScanner()
        mock_resp = MagicMock()
        mock_resp.status_code = 404

        client = AsyncMock()
        client.get.return_value = mock_resp

        result = await scanner.scan_username("nonexistent", client)
        assert result is not None
        assert result.exists is False
```

## Step 5: Verify

```bash
# Run your test
poetry run pytest tests/test_newplatform_scanner.py -v

# Run the full suite
poetry run pytest tests/ -v

# Lint
poetry run ruff check src/adapters/osint_sources/newplatform.py
```

## Tips

- **Use the `metadata` dict** for platform-specific data (followers, repos, karma, etc.)
- **Populate `bio`** when available — the AI uses it for cognitive profiling
- **Set `image_url`** for the PDF dossier identity card
- **Check `HIGH_SIGNAL_PLATFORMS`** in `graph_exporter.py` — add your platform if it provides meaningful intelligence signals
