"""Language utilities for OSINT-D2.

This module centralizes the language options supported across the
application. Keeping it in the domain layer allows both CLI and service
layers to share a single source of truth without creating circular
imports with adapters.
"""

from __future__ import annotations

from enum import Enum


class Language(str, Enum):
    """Supported natural-language choices for user-facing output."""

    ENGLISH = "en"
    SPANISH = "es"

    @classmethod
    def default(cls) -> "Language":
        """Return the default language used across the application."""

        return cls.ENGLISH

    @classmethod
    def from_bool(cls, spanish: bool) -> "Language":
        """Derive a language value from a boolean flag."""

        return cls.SPANISH if spanish else cls.ENGLISH

    def label(self) -> str:
        """Human readable label for prompts and logging."""

        return "Spanish" if self is Language.SPANISH else "English"
