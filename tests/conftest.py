"""Shared test setup."""

from __future__ import annotations

import pytest

from core.config import AppSettings


@pytest.fixture(autouse=True)
def _ignore_real_env_files(monkeypatch):
    """Keep tests away from the developer's keys, which would make real, paid API calls."""
    monkeypatch.setitem(AppSettings.model_config, "env_file", None)
