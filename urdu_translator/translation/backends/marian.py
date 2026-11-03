"""Local Marian Urdu-to-English backend.

Weights are read from the model folder selected by engine.json. Nothing in
this module contacts a model hub. PyTorch is imported only when a translation
starts, so the window can open without those libraries.
"""

from __future__ import annotations

import importlib.util
import os
import re
from pathlib import Path

from urdu_translator.errors import TranslationFailedError
from urdu_translator.translation.context import choose_contextual_line, needs_neighbor_context
from urdu_translator.translation.engine import TranslationEngine
from urdu_translator.translation.package import ModelPackage
from urdu_translator.translation.registry import register_backend
from urdu_translator.translation.terminology import Terminology, terminology_from_package

BACKEND_KEY = "marian"

_FILE_GROUPS = (
    ("config.json",),
    ("pytorch_model.bin", "model.safetensors"),
    ("source.spm", "tokenizer.json", "vocab.json"),
)


class MarianEngine(TranslationEngine):
    """Batch translator for one local Marian checkpoint."""

    def __init__(self, package: ModelPackage, model, tokenizer, device: str, terminology: Terminology) -> None:
        super().__init__(package)
        self.model = model
        self.tokenizer = tokenizer
        self.device = device
        self.terminology = terminology
        self.num_beams = _positive_int(package.options.get("num_beams"), "num_beams", 2)
        self.max_new_tokens = _positive_int(package.options.get("max_new_tokens"), "max_new_tokens", 256)
        self.max_input_length = _positive_int(package.options.get("max_input_length"), "max_input_length", 256)
        self.preferred_batch_size = _positive_int(package.options.get("batch_size"), "batch_size", 8)

    def translate_batch(self, texts: list[str]) -> list[str]:
        return self._translate_prepared(texts, mode="literal")

    def translate_in_context(self, texts: list[str], contexts: list[str]) -> list[str]:
        """Translate short replies with the previous Urdu line available to the model."""
        if len(contexts) != len(texts):
            raise TranslationFailedError("The translation engine received incomplete context.")
        results = [""] * len(texts)
        solo_slots = [index for index, text in enumerate(texts) if not _use_context(text, contexts[index])]
        pair_slots = [index for index in range(len(texts)) if index not in set(solo_slots)]
        if solo_slots:
            solos = self._translate_prepared([texts[index] for index in solo_slots], mode="contextual")
            for index, value in zip(solo_slots, solos, strict=True):
                results[index] = value
        if pair_slots:
            solos = self._translate_prepared([texts[index] for index in pair_slots], mode="contextual")
            combined = [
                f"{contexts[index].rstrip()} {texts[index].lstrip()}"
                for index in pair_slots
            ]
            pairs = self._generate(combined)
            for index, solo, pair in zip(pair_slots, solos, pairs, strict=True):
                results[index] = choose_contextual_line(solo, pair)
        return results

    def _translate_prepared(self, texts: list[str], *, mode: str) -> list[str]:
        if not texts:
            return []
        plans = [self.terminology.plan(text, mode) for text in texts]
        pending = [part for plan in plans for kind, part in plan if kind == "translate"]
        generated = self._generate(pending) if pending else []
        if len(generated) != len(pending):
            raise TranslationFailedError("The translation engine returned an unexpected result.")
        cursor = 0
        results: list[str] = []
        for plan in plans:
            pieces: list[str] = []
            for kind, part in plan:
                if kind == "translate":
                    pieces.append(generated[cursor])
                    cursor += 1
                else:
                    pieces.append(part)
            results.append(_join_pieces(pieces))
        return results

    def _generate(self, texts: list[str]) -> list[str]:
        import torch

        inputs = self.tokenizer(
            texts,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=self.max_input_length,
        )
        inputs = {name: value.to(self.device) for name, value in inputs.items()}
        with torch.inference_mode():
            output_tokens = self.model.generate(
                **inputs,
                num_beams=self.num_beams,
                max_new_tokens=self.max_new_tokens,
            )
        decoded = self.tokenizer.batch_decode(output_tokens, skip_special_tokens=True)
        return [" ".join(str(line).replace("\n", " ").split()) for line in decoded]


def register() -> None:
    """Register this backend. Called when the backends package is imported."""
    register_backend(BACKEND_KEY, load_marian_engine, probe=readiness_issue)


def load_marian_engine(package: ModelPackage) -> MarianEngine:
    """Load weights from the package directory and return an engine."""
    folder = model_folder(package)
    missing = missing_weight_files(folder)
    if missing:
        raise TranslationFailedError(missing_weights_message(folder, missing))
    _require_libraries()
    _block_network()
    terminology = terminology_from_package(package.directory, package.options.get("terminology"))
    device = resolve_device(str(package.options.get("device", "auto")))
    model, tokenizer = _load_local_checkpoint(folder, device)
    return MarianEngine(package, model, tokenizer, device, terminology)


def readiness_issue(package: ModelPackage) -> str | None:
    """Describe a setup problem without loading weights."""
    try:
        folder = model_folder(package)
    except TranslationFailedError as exc:
        return str(exc)
    missing = missing_weight_files(folder)
    if missing:
        return missing_weights_message(folder, missing)
    if not _libraries_installed():
        return library_message()
    return None


def model_folder(package: ModelPackage) -> Path:
    """Resolve the weight folder and keep it inside the model package."""
    raw = package.options.get("model_path", ".")
    if not isinstance(raw, str) or not raw.strip():
        raise TranslationFailedError("\"model_path\" must be a folder inside the model package.")
    path = Path(raw)
    if path.is_absolute():
        raise TranslationFailedError("The model path must stay inside the model folder.")
    root = package.directory.resolve()
    resolved = (root / path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise TranslationFailedError("The model path must stay inside the model folder.") from exc
    return resolved


def missing_weight_files(folder: Path) -> list[str]:
    """Return human-readable groups of files that are not in ``folder``."""
    missing: list[str] = []
    for group in _FILE_GROUPS:
        if not any((folder / name).is_file() for name in group):
            missing.append(" or ".join(group))
    return missing


def resolve_device(requested: str, *, cuda_available: bool | None = None) -> str:
    """Choose ``cpu`` or ``cuda`` from the package setting."""
    if cuda_available is None:
        cuda_available = _cuda_available()
    choice = requested.strip().lower() or "auto"
    if choice == "auto":
        return "cuda" if cuda_available else "cpu"
    if choice == "cpu":
        return "cpu"
    if choice in {"cuda", "gpu"}:
        if not cuda_available:
            raise TranslationFailedError("GPU was requested, but no CUDA device is available. Use \"cpu\" or \"auto\".")
        return "cuda"
    raise TranslationFailedError(f"Unknown device setting \"{requested}\". Use auto, cpu, or cuda.")


def missing_weights_message(folder: Path, missing: list[str]) -> str:
    listed = ", ".join(missing)
    return (
        f"The model folder {folder} is missing {listed}. "
        "Copy the local Marian weight files into that folder. "
        "This application does not download them."
    )


def library_message() -> str:
    return (
        "The Marian backend needs PyTorch, Transformers, and SentencePiece installed locally. "
        "The window does not install or download them."
    )


def _libraries_installed() -> bool:
    return all(importlib.util.find_spec(name) is not None for name in ("torch", "transformers", "sentencepiece"))


def _require_libraries() -> None:
    if not _libraries_installed():
        raise TranslationFailedError(library_message())


def _cuda_available() -> bool:
    if importlib.util.find_spec("torch") is None:
        return False
    import torch

    return bool(torch.cuda.is_available())


def _block_network() -> None:
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_DATASETS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"


def _load_local_checkpoint(folder: Path, device: str):
    import torch
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    try:
        tokenizer = AutoTokenizer.from_pretrained(str(folder), local_files_only=True)
        model = AutoModelForSeq2SeqLM.from_pretrained(str(folder), local_files_only=True)
    except Exception as exc:
        raise TranslationFailedError(f"The model in {folder} could not be read. {exc}") from exc
    if device == "cuda":
        model = model.half()
    model.to(device)
    model.eval()
    return model, tokenizer


_PUNCTUATION = str.maketrans({"،": ",", "؛": ";", "؟": "?", "۔": "."})


def _join_pieces(pieces: list[str]) -> str:
    """Join kept and translated pieces without gluing words together."""
    combined = ""
    for raw in pieces:
        piece = raw.translate(_PUNCTUATION)
        if not piece:
            continue
        stripped = piece.strip()
        if len(stripped) == 1 and stripped in ".!?" and combined.rstrip().endswith(stripped):
            continue
        if combined and combined[-1].isalnum() and piece[0].isalnum():
            combined += " "
        combined += piece
    combined = re.sub(r"[ \t]{2,}", " ", combined)
    combined = re.sub(r"\s+([,.!?;:])", r"\1", combined)
    return combined.strip()


def _use_context(text: str, context: str) -> bool:
    return bool(context.strip()) and needs_neighbor_context(text)


def _positive_int(value: object, name: str, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise TranslationFailedError(f"\"{name}\" must be a positive integer.")
    return value
