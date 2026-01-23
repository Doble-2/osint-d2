"""Operaciones sobre input para listas data-driven.

Implementa un subset práctico de operaciones comunes.
"""

from __future__ import annotations

import hashlib
from urllib.parse import quote


def apply_input_operation(value: str, operation: str | None) -> str:
    v = value
    if operation is None:
        return v

    op = operation.strip().lower()

    if op in ("identity", "none", "noop"):
        return v
    if op == "lower":
        return v.lower()
    if op == "strip":
        return v.strip()
    if op in ("urlencode", "url-encode", "url_encode"):
        return quote(v)

    # Hashes (frecuentes en listas de email).
    if op in ("hash-md5", "md5"):
        return hashlib.md5(v.encode("utf-8")).hexdigest()  # nosec
    if op in ("hash-sha1", "sha1"):
        return hashlib.sha1(v.encode("utf-8")).hexdigest()  # nosec
    if op in ("hash-sha256", "sha256"):
        return hashlib.sha256(v.encode("utf-8")).hexdigest()

    # Si no reconocemos la operación, devolvemos el input sin tocar.
    return v
