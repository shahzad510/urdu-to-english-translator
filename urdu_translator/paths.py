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
    the folder that contains the executable.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def models_dir() -> Path:
    """Local directory scanned for translation model packages.

    Windows stores engine packages under the user's LocalAppData folder.
    Linux retains the existing project/install models directory.
    """
    override = os.environ.get("URDU_TRANSLATOR_MODELS")
    if override:
        return Path(override).expanduser()

    if _windows():
        return recommended_models_dir()

    return install_root() / "models"


def fonts_dir() -> Path:
    """Bundled fonts shipped with the application."""
    return package_dir() / "resources" / "fonts"


def _windows() -> bool:
    return sys.platform == "win32"


def user_data_dir() -> Path:
    """Per-user folder for history, logs, and configuration.

    Linux keeps the existing XDG location. Windows uses LocalAppData and
    never writes user data into Program Files.
    """
    override = os.environ.get("URDU_TRANSLATOR_DATA")
    if override:
        path = Path(override).expanduser()
    elif _windows():
        base = os.environ.get("LOCALAPPDATA")
        if not base:
            base = str(Path.home() / "AppData" / "Local")
        path = Path(base) / "UrduTranslator"
    else:
        base = os.environ.get(
            "XDG_DATA_HOME",
            str(Path.home() / ".local" / "share")
        )
        path = Path(base) / "urdu-translator"

    path.mkdir(parents=True, exist_ok=True)
    return path


def _ensure(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_dir() -> Path:
    """Configuration files. On Linux these stay in the existing data folder."""
    if _windows():
        return _ensure(user_data_dir() / "Configuration")
    return user_data_dir()


def history_dir() -> Path:
    """Folder that holds the history database on Windows."""
    if _windows():
        return _ensure(user_data_dir() / "History")
    return user_data_dir()


def logs_dir() -> Path:
    """Folder that holds the application log on Windows."""
    if _windows():
        return _ensure(user_data_dir() / "Logs")
    return user_data_dir()


def temp_dir() -> Path:
    """Scratch files for this user. Not used for the GGUF model."""
    if _windows():
        return _ensure(user_data_dir() / "Temp")
    return _ensure(user_data_dir() / "tmp")


def recommended_models_dir() -> Path:
    """Preferred place to keep a local copy of the GGUF model.

    On Windows this is:
    %LOCALAPPDATA%\\UrduTranslator\\Models

    The original file on a USB drive is never the install directory.
    """
    if _windows():
        return _ensure(user_data_dir() / "Models")
    return _ensure(user_data_dir() / "models")


def database_path() -> Path:
    """SQLite file that stores translation history."""
    override = os.environ.get("URDU_TRANSLATOR_DATABASE")
    if override:
        return Path(override).expanduser()

    if _windows():
        return history_dir() / "history.db"

    return user_data_dir() / "history.db"


def log_path() -> Path:
    """Diagnostic log. Source text is not written here."""
    if _windows():
        return logs_dir() / "application.log"
    return user_data_dir() / "application.log"


def window_settings_path() -> Path:
    """Ini file for the window size. On Linux this stays beside the history file."""
    if _windows():
        return config_dir() / "window.ini"
    return user_data_dir() / "window.ini"


def bundled_llama_server() -> Path | None:
    """A llama-server binary shipped beside the application, when one is present."""
    name = "llama-server.exe" if _windows() else "llama-server"
    roots: list[Path] = []

    if getattr(sys, "frozen", False):
        roots.append(Path(sys.executable).resolve().parent)
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            roots.append(Path(meipass))

    roots.append(install_root() / "runtime")
    roots.append(install_root())

    for root in roots:
        candidate = root / name
        if candidate.is_file():
            return candidate

    return None