"""Locations for models, history, and bundled resources.

The running application reads only these local paths. Model files are resolved
from disk and are never fetched.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def package_dir() -> Path:
    """Directory that contains this package's modules and resources."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS")) / "urdu_translator"
    return Path(__file__).resolve().parent


def install_root() -> Path:
    """Folder that holds the editable models directory.

    In a source checkout this is the project root. In a packaged build it is
    the folder that contains the executable, so a model can be added beside
    the application without rebuilding it.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def models_dir() -> Path:
    """Local directory scanned for translation model packages."""
    override = os.environ.get("URDU_TRANSLATOR_MODELS")
    if override:
        return Path(override).expanduser()
    return install_root() / "models"


def fonts_dir() -> Path:
    """Bundled fonts shipped with the application."""
    return package_dir() / "resources" / "fonts"


def user_data_dir() -> Path:
    """Per-user folder for the history database and the application log."""
    override = os.environ.get("URDU_TRANSLATOR_DATA")
    if override:
        path = Path(override).expanduser()
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        path = base / "UrduTranslator"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        path = base / "urdu-translator"
    path.mkdir(parents=True, exist_ok=True)
    return path


def database_path() -> Path:
    """SQLite file that stores translation history."""
    override = os.environ.get("URDU_TRANSLATOR_DATABASE")
    if override:
        return Path(override).expanduser()
    return user_data_dir() / "history.db"
