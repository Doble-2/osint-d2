"""Contratos de scanners OSINT.

Por qué Protocol:
- Define un contrato estructural (duck typing) sin herencia rígida.
- Permite que adaptadores (Sherlock-like, GitHub, etc.) sean intercambiables
  y testeables sin acoplar el Core a implementaciones concretas.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from core.domain.models import SocialProfile


@runtime_checkable
class OSINTScanner(Protocol):
    """Contrato mínimo para un módulo de búsqueda.

    Reglas de diseño:
    - `scan` es asíncrono porque típicamente hará I/O (HTTP).
    - Devuelve un único `SocialProfile` por red/fuente.
    """

    async def scan(self, username: str) -> SocialProfile:
        """Escanea la fuente para un `username` y devuelve el resultado normalizado."""

        ...
