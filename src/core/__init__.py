"""Capa Core.

Por qué existe:
- Aísla la lógica de negocio y el dominio de los detalles de infraestructura.
- Facilita testeo, extensibilidad y sustitución de adaptadores (Clean Architecture).
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("osint-d2")
except PackageNotFoundError:
    # Running from source or from the PyInstaller bundle.
    __version__ = "3.0.0"
