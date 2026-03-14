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
    PORTUGUESE = "pt"
    ARABIC = "ar"
    RUSSIAN = "ru"

    @classmethod
    def default(cls) -> "Language":
        """Return the default language used across the application."""

        return cls.ENGLISH

    @classmethod
    def from_str(cls, value: str) -> "Language":
        """Parse a string into a Language, case-insensitive."""

        value = value.strip().lower()
        for lang in cls:
            if value in (lang.value, lang.name.lower()):
                return lang
        raise ValueError(f"Unsupported language: {value}")

    def label(self) -> str:
        """Human readable label for prompts and logging."""
        Language = self.__class__
        if self == Language.ENGLISH:
            return "English"
        elif self == Language.SPANISH:
            return "Spanish"
        elif self == Language.PORTUGUESE:
            return "Portuguese"
        elif self == Language.ARABIC:
            return "Arabic"
        elif self == Language.RUSSIAN:
            return "Russian"
        return Language(self.value).name.capitalize()
