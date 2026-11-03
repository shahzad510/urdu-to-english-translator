"""Model package description shared by the loader and translation backends."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ModelPackage:
    """A local model folder discovered from engine.json.

    ``options`` holds any extra keys from that file so a backend can read
    paths and runtime settings without the window knowing them.
    """

    name: str
    backend: str
    directory: Path
    source_language: str
    target_language: str
    is_default: bool
    options: dict[str, Any]
    role: str = "literal"
