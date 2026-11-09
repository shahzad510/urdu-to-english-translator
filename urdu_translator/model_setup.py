"""Locate, check, and optionally copy the external Gemma GGUF file.

The model is never downloaded. A path chosen by the user is stored in the
per-user configuration directory. The original file is only read.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from urdu_translator.errors import TranslationFailedError
from urdu_translator.paths import (
    config_dir,
    models_dir,
    recommended_models_dir,
)
from urdu_translator.translation.backends.llama_server import (
    EXPECTED_GGUF,
    LOCAL_HOST,
    LlamaServer,
    ServerSettings,
    missing_binary_message,
    missing_model_message,
)

Progress = Callable[[int, int], None]
READY_STATUS = "AI Model Ready — Offline Mode"
_CHUNK = 1024 * 1024

GEMMA_PACKAGE_NAME = "gemma-4-e4b"


def model_config_path() -> Path:
    """JSON file that remembers the GGUF location."""
    return config_dir() / "model.json"


def load_saved_model_path() -> Path | None:
    """Return the configured GGUF path, or None when the user has not chosen one."""
    path = model_config_path()
    if not path.is_file():
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(loaded, dict):
        return None
    raw = loaded.get("model_path")
    if not isinstance(raw, str) or not raw.strip():
        return None
    return Path(raw).expanduser()


def save_model_path(model: Path) -> None:
    """Remember a model path. This does not move or delete the file."""
    destination = model_config_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {"model_path": str(Path(model).expanduser())}
    destination.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )


def register_gemma_engine() -> Path:
    """Create or update the local Gemma engine package configuration.

    The GGUF itself remains in the user's model folder. This file registers
    the Gemma backend with the application.
    """
    package_dir = models_dir() / GEMMA_PACKAGE_NAME
    package_dir.mkdir(parents=True, exist_ok=True)

    engine_config = {
        "name": "Gemma 4 E4B",
        "backend": "gemma",
        "source_language": "ur",
        "target_language": "en",
        "default": True,
        "role": "literal",
        "host": LOCAL_HOST,
        "port": 8080,
        "context_length": 8192,
        "threads": 4,
        "max_new_tokens": 2048,
        "overlap_lines": 2,
        "temperature": 0.2,
    }

    destination = package_dir / "engine.json"
    temporary = destination.with_name("engine.json.tmp")

    try:
        temporary.write_text(
            json.dumps(engine_config, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(destination)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise TranslationFailedError(
            f"The Gemma engine configuration could not be created. {exc}"
        ) from exc

    return destination


def unavailable_model_message(model: Path) -> str:
    """Explain a missing file without offering an online model."""
    return (
        f"The Gemma model is unavailable: {model}. "
        f"Reconnect the drive that contains {EXPECTED_GGUF}, or browse for another copy. "
        "The application does not download a model and does not use an online service."
    )


def validate_model_file(model: Path) -> str | None:
    """Return an error when the file cannot be used, or None when it can be opened.

    Validity is file access, the .gguf suffix, a non-empty GGUF header, and a
    later load by llama-server. There is no fixed-size requirement.
    """
    path = Path(model)
    if not path.exists():
        return unavailable_model_message(path)
    if path.suffix.lower() != ".gguf":
        return (
            f"Choose the Gemma model file named {EXPECTED_GGUF}. "
            "The file name must end in .gguf."
        )
    if not path.is_file():
        return f"{path} is not a file."
    try:
        with path.open("rb") as handle:
            header = handle.read(4)
    except OSError as exc:
        return f"The model file cannot be read: {path}. {exc}"
    if not header:
        return f"The model file is empty: {path}."
    if header != b"GGUF":
        return f"{path.name} is not a GGUF model file."
    return None


def copy_model_file(
    source: Path,
    destination_dir: Path | None = None,
    progress: Progress | None = None,
) -> Path:
    """Copy a GGUF into the recommended folder and check that the sizes match.

    The source file is left unchanged.
    """
    original = Path(source)
    problem = validate_model_file(original)
    if problem:
        raise TranslationFailedError(problem)

    folder = (
        Path(destination_dir)
        if destination_dir is not None
        else recommended_models_dir()
    )
    folder.mkdir(parents=True, exist_ok=True)

    target = folder / original.name
    temporary = target.with_name(target.name + ".partial")
    total = original.stat().st_size
    copied = 0

    try:
        with original.open("rb") as incoming, temporary.open("wb") as outgoing:
            while True:
                block = incoming.read(_CHUNK)
                if not block:
                    break
                outgoing.write(block)
                copied += len(block)
                if progress is not None:
                    progress(copied, total)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise TranslationFailedError(
            f"The model could not be copied. {exc}"
        ) from exc

    copied_size = temporary.stat().st_size
    if copied_size != total:
        temporary.unlink(missing_ok=True)
        raise TranslationFailedError(
            "The copied model does not match the original file size. "
            "The USB file was not changed."
        )

    temporary.replace(target)

    if target.stat().st_size != original.stat().st_size:
        raise TranslationFailedError(
            "The copied model does not match the original file size. "
            "The USB file was not changed."
        )

    return target


def confirm_server_can_open(model: Path, binary: Path) -> str | None:
    """Ask the local llama-server to load the file. None means /health succeeded.

    The server listens on 127.0.0.1. A failure is returned as text so the
    setup dialog can show it. Nothing is downloaded.
    """
    problem = validate_model_file(model)
    if problem:
        return problem

    program = Path(binary)
    if not program.is_file():
        return missing_binary_message(program)

    settings = ServerSettings(
        binary=program,
        model=Path(model),
        host=LOCAL_HOST,
    )

    if settings.host != LOCAL_HOST:
        return "The translation server listens on 127.0.0.1 only."

    try:
        LlamaServer(settings).ensure_started()
    except TranslationFailedError as exc:
        return str(exc)
    except OSError as exc:
        return f"{missing_binary_message(program)} {exc}"

    return None


def configured_model_status(model: Path | None) -> tuple[str, str]:
    """Short state and sentence for a saved or selected model path."""
    if model is None:
        return "missing", missing_model_message(Path(EXPECTED_GGUF))

    problem = validate_model_file(model)
    if problem:
        return "unavailable", problem

    return "ready", READY_STATUS