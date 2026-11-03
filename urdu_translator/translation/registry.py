"""Registry of offline translation backends.

Importing a backend module should call :func:`register_backend`. The loader
looks up the ``backend`` value from engine.json and never exposes that key
in the window.
"""

from __future__ import annotations

from collections.abc import Callable

from urdu_translator.translation.engine import TranslationEngine
from urdu_translator.translation.package import ModelPackage

BackendFactory = Callable[[ModelPackage], TranslationEngine]
BackendProbe = Callable[[ModelPackage], str | None]

_FACTORIES: dict[str, BackendFactory] = {}
_PROBES: dict[str, BackendProbe] = {}


def register_backend(key: str, factory: BackendFactory, *, probe: BackendProbe | None = None) -> None:
    """Register ``factory`` under the backend key used in engine.json.

    ``probe`` may describe a setup problem without loading model weights.
    """
    cleaned = key.strip()
    if not cleaned:
        raise ValueError("A backend key is required.")
    _FACTORIES[cleaned] = factory
    if probe is None:
        _PROBES.pop(cleaned, None)
    else:
        _PROBES[cleaned] = probe


def unregister_backend(key: str) -> None:
    """Remove a backend registration. Used by tests and hot-reload tooling."""
    _FACTORIES.pop(key, None)
    _PROBES.pop(key, None)


def probe_backend(key: str, package: ModelPackage) -> str | None:
    """Return a setup message, or None when the package can be loaded."""
    probe = _PROBES.get(key)
    if probe is None:
        return None
    return probe(package)


def get_backend(key: str) -> BackendFactory | None:
    """Return the factory for ``key``, or None when it is not registered."""
    return _FACTORIES.get(key)


def registered_backends() -> tuple[str, ...]:
    """Sorted backend keys currently registered in this process."""
    return tuple(sorted(_FACTORIES))
