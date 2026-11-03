"""Local IndicTrans2 Urdu-to-English backend.

Weights are read from the model folder selected by engine.json. Nothing in
this module contacts a model hub. The heavy libraries are imported only when
a translation starts, so the window can open without them.

This backend is optional. The OPUS-MT Marian backend remains the literal model.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

from urdu_translator.errors import TranslationFailedError
from urdu_translator.translation.backends.marian import resolve_device
from urdu_translator.translation.context import choose_contextual_line, needs_neighbor_context
from urdu_translator.translation.engine import TranslationEngine
from urdu_translator.translation.package import ModelPackage
from urdu_translator.translation.registry import register_backend
from urdu_translator.translation.terminology import Terminology, terminology_from_package

BACKEND_KEY = "indictrans2"

_FILE_GROUPS = (
    ("config.json",),
    ("pytorch_model.bin", "model.safetensors"),
    ("tokenizer_config.json", "tokenizer.json", "vocab.json"),
)


class IndicTransEngine(TranslationEngine):
    """Batch translator for one local IndicTrans2 checkpoint."""

    def __init__(self, package: ModelPackage, model, tokenizer, processor, device: str, terminology: Terminology) -> None:
        super().__init__(package)
        self.model = model
        self.tokenizer = tokenizer
        self.processor = processor
        self.device = device
        self.terminology = terminology
        self.src_lang = str(package.options.get("src_lang") or "urd_Arab")
        self.tgt_lang = str(package.options.get("tgt_lang") or "eng_Latn")
        self.num_beams = _positive_int(package.options.get("num_beams"), "num_beams", 5)
        self.max_new_tokens = _positive_int(package.options.get("max_new_tokens"), "max_new_tokens", 256)
        self.max_input_length = _positive_int(package.options.get("max_input_length"), "max_input_length", 256)
        self.preferred_batch_size = _positive_int(package.options.get("batch_size"), "batch_size", 4)

    def translate_batch(self, texts: list[str]) -> list[str]:
        return self._translate_prepared(texts, mode="literal")

    def translate_in_context(self, texts: list[str], contexts: list[str]) -> list[str]:
        if len(contexts) != len(texts):
            raise TranslationFailedError("The translation engine received incomplete context.")
        results = [""] * len(texts)
        solo_slots = [index for index, text in enumerate(texts) if not (contexts[index].strip() and needs_neighbor_context(text))]
        pair_slots = [index for index in range(len(texts)) if index not in set(solo_slots)]
        if solo_slots:
            solos = self._translate_prepared([texts[index] for index in solo_slots], mode="contextual")
            for index, value in zip(solo_slots, solos, strict=True):
                results[index] = value
        if pair_slots:
            solos = self._translate_prepared([texts[index] for index in pair_slots], mode="contextual")
            combined = [f"{contexts[index].rstrip()} {texts[index].lstrip()}" for index in pair_slots]
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

        prepared = self.processor.preprocess_batch(texts, src_lang=self.src_lang, tgt_lang=self.tgt_lang)
        inputs = self.tokenizer(
            prepared,
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
        restored = self.processor.postprocess_batch(decoded, lang=self.tgt_lang)
        return [" ".join(str(line).replace("\n", " ").split()) for line in restored]


def register() -> None:
    """Register this backend. Called when the backends package is imported."""
    register_backend(BACKEND_KEY, load_indictrans_engine, probe=readiness_issue)


def load_indictrans_engine(package: ModelPackage) -> IndicTransEngine:
    """Load weights from the package directory and return an engine."""
    folder = model_folder(package)
    missing = missing_weight_files(folder)
    if missing:
        raise TranslationFailedError(missing_weights_message(folder, missing))
    _require_libraries()
    _block_network()
    terminology = terminology_from_package(package.directory, package.options.get("terminology"))
    device = resolve_device(str(package.options.get("device", "auto")))
    model, tokenizer, processor = _load_local_checkpoint(folder, device)
    return IndicTransEngine(package, model, tokenizer, processor, device, terminology)


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
    raw = package.options.get("model_dir", ".")
    if not isinstance(raw, str) or not raw.strip():
        raise TranslationFailedError("The model folder setting must be a path inside the package.")
    path = Path(raw)
    if path.is_absolute():
        raise TranslationFailedError("The model folder must stay inside the package directory.")
    resolved = (package.directory / path).resolve()
    try:
        resolved.relative_to(package.directory.resolve())
    except ValueError as exc:
        raise TranslationFailedError("The model folder must stay inside the package directory.") from exc
    return resolved


def missing_weight_files(folder: Path) -> list[str]:
    missing: list[str] = []
    for group in _FILE_GROUPS:
        if not any((folder / name).is_file() for name in group):
            missing.append(" or ".join(group))
    return missing


def missing_weights_message(folder: Path, missing: list[str]) -> str:
    listed = ", ".join(missing)
    return (
        f"The contextual model folder {folder} is missing {listed}. "
        "Copy the local IndicTrans2 weight files into that folder. "
        "This application does not download them."
    )


def local_install_report(folder: Path) -> str:
    """Describe the local IndicTrans2 folder. This does not contact the network."""
    folder = Path(folder)
    lines = [
        f"Folder: {folder}",
        "Licence: MIT, AI4Bharat. Keep NOTICE.txt with the weights. Commercial use is allowed.",
        "Disk for the distilled checkpoint: about 1 GB. RAM once loaded: about 3–4 GB.",
        "CPU is supported. Set device to auto, cpu, or cuda in engine.json. CUDA is optional.",
        "The application does not download these weights.",
    ]
    lines.append("NOTICE.txt is present." if (folder / "NOTICE.txt").is_file() else "NOTICE.txt is missing.")
    lines.append("engine.json is present." if (folder / "engine.json").is_file() else "engine.json is missing.")
    missing = missing_weight_files(folder)
    if missing:
        lines.append("Weights are not installed: " + ", ".join(missing))
    else:
        lines.append("Weight files named by the backend are present.")
    missing_libraries = _missing_libraries()
    if missing_libraries:
        lines.append("Missing Python packages: " + ", ".join(missing_libraries) + ". The window does not install them.")
    else:
        lines.append("PyTorch, Transformers, SentencePiece, and IndicTransToolkit are installed.")
    return "\n".join(lines)


def library_message() -> str:
    missing = ", ".join(_missing_libraries()) or "PyTorch, Transformers, SentencePiece, and IndicTransToolkit"
    return (
        f"The contextual backend needs {missing} installed locally. "
        "The window does not install or download them."
    )


def _missing_libraries() -> list[str]:
    names = ("torch", "transformers", "sentencepiece", "IndicTransToolkit")
    return [name for name in names if importlib.util.find_spec(name) is None]


def _libraries_installed() -> bool:
    return not _missing_libraries()


def _require_libraries() -> None:
    if not _libraries_installed():
        raise TranslationFailedError(library_message())


def _block_network() -> None:
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_DATASETS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"


def _load_local_checkpoint(folder: Path, device: str):
    import torch
    from IndicTransToolkit.processor import IndicProcessor
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    try:
        tokenizer = AutoTokenizer.from_pretrained(str(folder), local_files_only=True, trust_remote_code=True)
        model = AutoModelForSeq2SeqLM.from_pretrained(str(folder), local_files_only=True, trust_remote_code=True)
        processor = IndicProcessor(inference=True)
    except Exception as exc:
        raise TranslationFailedError(f"The model in {folder} could not be read. {exc}") from exc
    if device == "cuda":
        model = model.half()
    model.to(device)
    model.eval()
    return model, tokenizer, processor


def _join_pieces(pieces: list[str]) -> str:
    combined = ""
    for piece in pieces:
        if not piece:
            continue
        if combined and combined[-1].isalnum() and piece[0].isalnum():
            combined += " "
        combined += piece
    combined = " ".join(combined.split())
    return combined.strip()


def _positive_int(value: object, name: str, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise TranslationFailedError(f"\"{name}\" must be a positive integer.")
    return value
