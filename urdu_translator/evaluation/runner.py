"""Translate one dataset with the active local engine.

Each item is timed on its own. A model that cannot be loaded records an
error and leaves its output empty. This module does not score accuracy.
OPUS-MT and IndicTrans2 stay recorded as not run. Their outputs are not
filled from Gemma.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from urdu_translator.errors import TranslationError
from urdu_translator.evaluation.dataset import EvalDataset, EvalItem
from urdu_translator.translation.loader import load_engine
from urdu_translator.translation.service import translate_document

Translator = Callable[[str], str]


@dataclass(frozen=True)
class ItemResult:
    """One item after a run. Empty output means that model did not translate it."""

    id: str
    source_ur: str
    reference_en: str
    opus_mt: str
    indictrans2: str
    notes: str
    opus_mt_seconds: float | None
    indictrans2_seconds: float | None
    opus_mt_error: str
    indictrans2_error: str
    gemma: str = ""
    gemma_seconds: float | None = None
    gemma_error: str = ""


@dataclass(frozen=True)
class ModelStatus:
    """Whether a model loaded, and how long that load took."""

    backend: str
    loaded: bool
    load_seconds: float | None
    error: str


@dataclass(frozen=True)
class EvaluationRun:
    """Outputs, timings, and errors for one dataset."""

    dataset_name: str
    description: str
    opus: ModelStatus
    indictrans2: ModelStatus
    gemma: ModelStatus
    items: list[ItemResult]


_NOT_INVOKED = (
    "This engine is not the active translator. Gemma is the only engine that runs, "
    "and a missing Gemma file is not filled from another model."
)


def evaluate_dataset(
    dataset: EvalDataset,
    *,
    opus: Translator | None,
    indictrans2: Translator | None,
    opus_status: ModelStatus,
    indictrans2_status: ModelStatus,
    gemma: Translator | None = None,
    gemma_status: ModelStatus | None = None,
) -> EvaluationRun:
    """Run the supplied translators. A missing translator records its status error."""
    if gemma_status is None:
        gemma_status = ModelStatus("gemma", False, None, "Gemma was not requested for this run.")
    items = [
        _translate_item(
            item,
            opus=opus,
            indictrans2=indictrans2,
            gemma=gemma,
            opus_error=opus_status.error,
            indictrans2_error=indictrans2_status.error,
            gemma_error=gemma_status.error,
        )
        for item in dataset.items
    ]
    return EvaluationRun(
        dataset_name=dataset.name,
        description=dataset.description,
        opus=opus_status,
        indictrans2=indictrans2_status,
        gemma=gemma_status,
        items=items,
    )


def run_local_models(dataset: EvalDataset, models_dir: Path) -> EvaluationRun:
    """Translate ``dataset`` with Gemma only.

    OPUS-MT and IndicTrans2 are recorded as not run. Their columns stay empty
    even when those folders are still on disk.
    """
    gemma_engine, gemma_status = _load_gemma(models_dir)
    skipped = ModelStatus("unused", False, None, _NOT_INVOKED)
    return evaluate_dataset(
        dataset,
        opus=None,
        indictrans2=None,
        opus_status=skipped,
        indictrans2_status=skipped,
        gemma=None if gemma_engine is None else _document_translator(gemma_engine),
        gemma_status=gemma_status,
    )


def _load_gemma(models_dir: Path) -> tuple[object | None, ModelStatus]:
    started = time.perf_counter()
    try:
        engine = load_engine(models_dir)
    except TranslationError as exc:
        return None, ModelStatus("gemma", False, None, str(exc))
    except Exception as exc:
        return None, ModelStatus("gemma", False, None, f"The model could not be loaded. {exc}")
    elapsed = time.perf_counter() - started
    backend = getattr(getattr(engine, "package", None), "backend", "")
    if backend != "gemma":
        return None, ModelStatus(
            str(backend or "unknown"),
            False,
            elapsed,
            "The active package is not Gemma. No other engine was run.",
        )
    return engine, ModelStatus("gemma", True, elapsed, "")


def _document_translator(engine: object) -> Translator:
    def translate(text: str) -> str:
        result = translate_document(text, lambda: engine, mode="literal")
        return result.text

    return translate


def _translate_item(
    item: EvalItem,
    *,
    opus: Translator | None,
    indictrans2: Translator | None,
    gemma: Translator | None,
    opus_error: str,
    indictrans2_error: str,
    gemma_error: str,
) -> ItemResult:
    opus_text, opus_seconds, opus_item_error = _timed(opus, item.source_ur, opus_error)
    indic_text, indic_seconds, indic_item_error = _timed(indictrans2, item.source_ur, indictrans2_error)
    gemma_text, gemma_seconds, gemma_item_error = _timed(gemma, item.source_ur, gemma_error)
    return ItemResult(
        id=item.id,
        source_ur=item.source_ur,
        reference_en=item.reference_en,
        opus_mt=opus_text,
        indictrans2=indic_text,
        notes=item.notes,
        opus_mt_seconds=opus_seconds,
        indictrans2_seconds=indic_seconds,
        opus_mt_error=opus_item_error,
        indictrans2_error=indic_item_error,
        gemma=gemma_text,
        gemma_seconds=gemma_seconds,
        gemma_error=gemma_item_error,
    )


def _timed(translator: Translator | None, text: str, unavailable: str) -> tuple[str, float | None, str]:
    if translator is None:
        return "", None, unavailable or "This model is not available."
    started = time.perf_counter()
    try:
        output = translator(text)
    except Exception as exc:
        return "", time.perf_counter() - started, str(exc)
    if not isinstance(output, str):
        return "", time.perf_counter() - started, "The translator did not return text."
    return output, time.perf_counter() - started, ""
