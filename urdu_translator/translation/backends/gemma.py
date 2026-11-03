"""Local Gemma 4 E4B backend.

Translation goes through the llama.cpp server named in engine.json. The GGUF
stays on its own drive. This module does not download it, does not load
llama-cpp-python, and does not switch to another engine when the file is missing.

The context length comes from engine.json and is 8192 in the supplied package.
"""

from __future__ import annotations

import inspect
import json
import os
from collections.abc import Callable
from pathlib import Path

from urdu_translator.errors import TranslationFailedError
from urdu_translator.translation.backends.llama_server import (
    LOCAL_HOST,
    ServerSettings,
    check_files,
    missing_binary_message,
    missing_model_message,
    shared_server,
)
from urdu_translator.translation.engine import TranslationEngine
from urdu_translator.translation.package import ModelPackage
from urdu_translator.translation.registry import register_backend
from urdu_translator.translation.terminology import Terminology, terminology_from_package

BACKEND_KEY = "gemma"
OFFICIAL_REPO = "google/gemma-4-E4B-it-qat-q4_0-gguf"
DEFAULT_CONTEXT = 8192
DEFAULT_MAX_NEW_TOKENS = 2048
DEFAULT_OVERLAP = 2
DEFAULT_TEMPERATURE = 0.2
EXPECTED_NAME = "gemma-4-E4B_q4_0-it.gguf"
CHUNK_CHAR_CAP = 1600

Completer = Callable[..., str]

_SYSTEM = (
    "You translate Urdu conversations into natural, professional English. "
    "Return only the translation. Do not add explanations, notes, titles, or commentary. "
    "Keep every speaker label exactly as written. "
    "Keep existing English words, abbreviations, codes, numbers, and identifiers unchanged. "
    "Return one output line for each input line, in the same order. "
    "Do not add facts that are not in the source. "
    "If a name, place, or technical term is ambiguous, copy it as written instead of guessing."
)


class GemmaEngine(TranslationEngine):
    """Chunk translator for one local Gemma GGUF file."""

    def __init__(
        self,
        package: ModelPackage,
        terminology: Terminology,
        complete: Completer,
        *,
        context_length: int,
        max_new_tokens: int,
        overlap_lines: int,
        max_chunk_chars: int,
        temperature: float,
    ) -> None:
        super().__init__(package)
        self.terminology = terminology
        self._complete = complete
        self.context_length = context_length
        self.max_new_tokens = max_new_tokens
        self.overlap_lines = overlap_lines
        self.max_chunk_chars = max_chunk_chars
        self.temperature = temperature
        self.n_gpu_layers = 0

    def translate_batch(self, texts: list[str]) -> list[str]:
        return [self.translate_chunk([text], [])[0] for text in texts]

    def translate_chunk(
        self,
        lines: list[str],
        context: list[str],
        should_stop: Callable[[], bool] | None = None,
    ) -> list[str]:
        """Translate ``lines`` as one passage. ``context`` is not repeated in the output."""
        if not lines:
            return []
        user = _user_prompt(lines, context, self.terminology)
        raw = _invoke_complete(self._complete, _SYSTEM, user, should_stop)
        if not isinstance(raw, str):
            raise TranslationFailedError("The translation model did not return text.")
        return split_translation(raw, len(lines))


def register() -> None:
    """Register this backend. Called when the backends package is imported."""
    register_backend(BACKEND_KEY, load_gemma_engine, probe=readiness_issue)


def load_gemma_engine(package: ModelPackage) -> GemmaEngine:
    """Prepare the local server. The process starts on the first translation."""
    issue = readiness_issue(package)
    if issue:
        raise TranslationFailedError(issue)
    runtime = _settings(package)
    model_path, server_bin = external_paths(package)
    _block_network()
    server = shared_server(
        ServerSettings(
            binary=server_bin,
            model=model_path,
            host=LOCAL_HOST,
            port=_port(package),
            context=int(runtime["context_length"]),
            threads=_threads(package),
            temperature=float(runtime["temperature"]),
            max_new_tokens=int(runtime["max_new_tokens"]),
        )
    )

    def complete(system: str, user: str, should_stop: Callable[[], bool] | None = None) -> str:
        return server.complete(system, user, should_stop=should_stop)

    terminology = terminology_from_package(package.directory, package.options.get("terminology"))
    return GemmaEngine(package, terminology, complete, **runtime)


def readiness_issue(package: ModelPackage) -> str | None:
    """Describe a setup problem without starting llama-server."""
    try:
        model_path, server_bin = external_paths(package)
        _port(package)
        _threads(package)
        if str(package.options.get("host") or LOCAL_HOST) != LOCAL_HOST:
            return "The translation server listens on 127.0.0.1 only."
        check_files(model_path, server_bin)
    except TranslationFailedError as exc:
        return str(exc)
    return None


def external_paths(package: ModelPackage) -> tuple[Path, Path]:
    """Read the absolute GGUF and llama-server paths from engine.json."""
    model = package.options.get("model_path")
    binary = package.options.get("server_bin")
    if not isinstance(model, str) or not model.strip():
        raise TranslationFailedError(missing_model_message(Path(EXPECTED_NAME)))
    if not isinstance(binary, str) or not binary.strip():
        raise TranslationFailedError(missing_binary_message(Path("llama-server")))
    model_path = Path(model).expanduser()
    server_bin = Path(binary).expanduser()
    if not model_path.is_absolute() or not server_bin.is_absolute():
        raise TranslationFailedError(
            "model_path and server_bin in engine.json must be absolute paths. "
            "The application does not copy the model into the project."
        )
    return model_path, server_bin


def cpu_only_layers(configured: object) -> int:
    """The server command does not move layers to a GPU."""
    return 0


def local_install_report(folder: Path) -> str:
    """Describe the Gemma package. This does not download anything or start the server."""
    root = Path(folder)
    lines = [
        f"Folder: {root}",
        "Checkpoint: official Google Q4_0 GGUF, "
        f"{OFFICIAL_REPO}.",
        "Licence: Apache 2.0 on the Gemma 4 model card. Keep the official licence "
        "and notices with the weights.",
        "Weights are about 4.5 GB and stay on the external drive. They are not copied "
        "into this folder. Runtime memory and the 8192-token context need additional RAM.",
        "Runtime: the external llama-server binary. It listens on 127.0.0.1:8080.",
    ]
    config = root / "engine.json"
    data: dict | None = None
    if config.is_file():
        try:
            loaded = json.loads(config.read_text(encoding="utf-8"))
            data = loaded if isinstance(loaded, dict) else None
            if data is None:
                lines.append("engine.json could not be read.")
        except (OSError, json.JSONDecodeError):
            lines.append("engine.json could not be read.")
    model_text = data.get("model_path") if data else None
    binary_text = data.get("server_bin") if data else None
    if not isinstance(model_text, str) or not model_text.strip():
        lines.append(
            f"Weight file not installed. The external drive or model file is unavailable: {EXPECTED_NAME}."
        )
    else:
        model_path = Path(model_text).expanduser()
        if model_path.is_file():
            lines.append(f"Weight file found: {model_path}")
        else:
            lines.append(
                f"Weight file not installed: {EXPECTED_NAME}. "
                "The external drive or model file is unavailable."
            )
    if not isinstance(binary_text, str) or not binary_text.strip():
        lines.append("llama-server not installed. Set server_bin in engine.json.")
    else:
        binary = Path(binary_text).expanduser()
        if binary.is_file():
            lines.append(f"llama-server found: {binary}")
        else:
            lines.append(f"llama-server not installed: {binary}")
    lines.append("This check does not download files. No other translation engine is used.")
    return "\n".join(lines)


def split_translation(text: str, expected: int) -> list[str]:
    """Take one model reply and require one line per source line."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        rows = cleaned.splitlines()
        if rows and rows[0].startswith("```"):
            rows = rows[1:]
        if rows and rows[-1].strip() == "```":
            rows = rows[:-1]
        cleaned = "\n".join(rows).strip("\n")
    parts = cleaned.splitlines()
    if len(parts) != expected:
        raise TranslationFailedError(
            "The translation did not return the same number of lines, so the "
            "document was not changed. Speaker names were left as written."
        )
    return parts


def _settings(package: ModelPackage) -> dict[str, int | float]:
    options = package.options
    context_length = _positive_int(options.get("context_length"), "context_length", DEFAULT_CONTEXT)
    max_new_tokens = _positive_int(options.get("max_new_tokens"), "max_new_tokens", DEFAULT_MAX_NEW_TOKENS)
    overlap_lines = _non_negative_int(options.get("overlap_lines"), "overlap_lines", DEFAULT_OVERLAP)
    temperature = _temperature(options.get("temperature"))
    configured = options.get("max_chunk_chars")
    if configured is None:
        # Keep the source chunk small enough for an 8192-token context, the
        # prompt, the overlap lines, and the reply.
        reserve = 2000 + overlap_lines * 200
        room = context_length - max_new_tokens - reserve
        max_chunk_chars = max(400, min(CHUNK_CHAR_CAP, room))
    else:
        max_chunk_chars = _positive_int(configured, "max_chunk_chars", 400)
    return {
        "context_length": context_length,
        "max_new_tokens": max_new_tokens,
        "overlap_lines": overlap_lines,
        "max_chunk_chars": max_chunk_chars,
        "temperature": temperature,
    }


def _user_prompt(lines: list[str], context: list[str], terminology: Terminology) -> str:
    parts: list[str] = []
    glossary = _glossary(terminology)
    if glossary:
        parts.append(glossary)
    if context:
        parts.append(
            "Earlier lines, for context only. Do not include them in the answer:\n"
            + "\n".join(context)
        )
    parts.append(
        f"Translate these lines. Return exactly {len(lines)} lines and nothing else:\n"
        + "\n".join(lines)
    )
    return "\n\n".join(parts)


def _glossary(terminology: Terminology) -> str:
    rows = [f"- {term.source} → {term.target}" for term in terminology.terms[:80]]
    if not rows:
        return ""
    return "Approved terminology. Use these wordings when the source uses them:\n" + "\n".join(rows)


def _invoke_complete(
    complete: Completer,
    system: str,
    user: str,
    should_stop: Callable[[], bool] | None,
) -> str:
    if "should_stop" in inspect.signature(complete).parameters:
        return complete(system, user, should_stop=should_stop)
    return complete(system, user)


def _port(package: ModelPackage) -> int:
    return _positive_int(package.options.get("port"), "port", 8080)


def _threads(package: ModelPackage) -> int:
    return _positive_int(package.options.get("threads"), "threads", 4)


def _block_network() -> None:
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_DATASETS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"


def _positive_int(value: object, name: str, default: int) -> int:
    if value is None:
        return default
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise TranslationFailedError(f"\"{name}\" must be a positive whole number.") from exc
    if number < 1:
        raise TranslationFailedError(f"\"{name}\" must be a positive whole number.")
    return number


def _non_negative_int(value: object, name: str, default: int) -> int:
    if value is None:
        return default
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise TranslationFailedError(f"\"{name}\" must be zero or a positive whole number.") from exc
    if number < 0:
        raise TranslationFailedError(f"\"{name}\" must be zero or a positive whole number.")
    return number


def _temperature(value: object) -> float:
    if value is None:
        return DEFAULT_TEMPERATURE
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise TranslationFailedError("\"temperature\" must be a number from 0 to 1.") from exc
    if number < 0 or number > 1:
        raise TranslationFailedError("\"temperature\" must be a number from 0 to 1.")
    return number
