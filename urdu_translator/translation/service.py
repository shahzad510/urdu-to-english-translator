"""Translate a whole document while keeping its line structure.

The service plans every line first. English-only lines are copied. Urdu lines
are sent to the engine in small batches on whatever thread calls this function.
The window calls it from a background worker.
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Callable
from dataclasses import dataclass

from urdu_translator.errors import (
    ModelNotFoundError,
    TranslationCancelled,
    TranslationError,
    TranslationFailedError,
    UnsupportedBackendError,
)
from urdu_translator.translation.chunks import plan_chunks, with_original_speaker
from urdu_translator.translation.engine import TranslationEngine
from urdu_translator.translation.segments import Segment, render_document, segment_document

logger = logging.getLogger("urdu_translator.translation")

# Small batches keep a future local model from holding a whole report at once
# and give the worker a chance to report progress between them.
TRANSLATION_BATCH_SIZE = 16

EngineLoader = Callable[[], TranslationEngine]
ProgressCallback = Callable[[str], None]
StopCallback = Callable[[], bool]


@dataclass(frozen=True)
class TranslationResult:
    """A finished document translation."""

    source_text: str
    text: str
    engine_name: str
    translated_segment_count: int
    passthrough_count: int


@dataclass(frozen=True)
class DualTranslationResult:
    """Literal and contextual translations of one document."""

    source_text: str
    literal: TranslationResult
    contextual: TranslationResult
    contextual_note: str = ""


def translate_both(
    text: str,
    load_literal: EngineLoader,
    load_contextual: EngineLoader,
    *,
    progress: ProgressCallback | None = None,
    should_stop: StopCallback | None = None,
) -> DualTranslationResult:
    """Translate once for each mode. A missing contextual model falls back."""
    shared: dict[str, TranslationEngine] = {}

    def literal_once() -> TranslationEngine:
        if "literal" not in shared:
            shared["literal"] = load_literal()
        return shared["literal"]

    note = ""

    def contextual_once() -> TranslationEngine:
        nonlocal note
        if "contextual" not in shared:
            try:
                shared["contextual"] = load_contextual()
            except (ModelNotFoundError, TranslationFailedError, UnsupportedBackendError) as exc:
                logger.info("Contextual model was not used: %s", exc)
                note = (
                    "No separate contextual model is ready. Contextual English is using the "
                    "literal model, with the previous Urdu line when a reply is short. "
                    "The application does not download models."
                )
                shared["contextual"] = literal_once()
        return shared["contextual"]

    literal = translate_document(
        text,
        literal_once,
        progress=_prefixed(progress, "Literal"),
        should_stop=should_stop,
        mode="literal",
    )
    contextual = translate_document(
        text,
        contextual_once,
        progress=_prefixed(progress, "Contextual"),
        should_stop=should_stop,
        mode="contextual",
    )
    return DualTranslationResult(
        source_text=text,
        literal=literal,
        contextual=contextual,
        contextual_note=note,
    )


def translate_document(
    text: str,
    load_engine: EngineLoader,
    *,
    progress: ProgressCallback | None = None,
    should_stop: StopCallback | None = None,
    mode: str = "literal",
) -> TranslationResult:
    """Translate Urdu lines in ``text`` and preserve the rest.

    ``load_engine`` is called only when at least one line needs translation,
    so an English-only document does not require a model.
    """
    segments = segment_document(text)
    pending = [segment.source_for_engine() for segment in segments if segment.needs_translation]
    contexts = _pending_contexts(segments) if mode == "contextual" else None
    passthrough_count = sum(not segment.needs_translation for segment in segments)

    if not pending:
        _report(progress, "No Urdu text to translate.")
        return TranslationResult(
            source_text=text,
            text=render_document(segments, []),
            engine_name="",
            translated_segment_count=0,
            passthrough_count=passthrough_count,
        )

    _stop_if_requested(should_stop)
    _report(progress, "Loading the translation model…")
    try:
        engine = load_engine()
    except TranslationError:
        raise
    except Exception as exc:
        raise TranslationFailedError(f"The translation model could not be loaded. {exc}") from exc

    if getattr(engine, "translate_chunk", None) is not None:
        rendered = _translate_grouped(segments, engine, progress, should_stop)
        return TranslationResult(
            source_text=text,
            text=rendered,
            engine_name=engine.name,
            translated_segment_count=len(pending),
            passthrough_count=passthrough_count,
        )

    translations: list[str] = []
    total = len(pending)
    batch_size = _batch_size(engine)
    for start in range(0, total, batch_size):
        _stop_if_requested(should_stop)
        batch = pending[start : start + batch_size]
        end = start + len(batch)
        batch_context = contexts[start:end] if contexts is not None else None
        _report(progress, f"Translating lines {start + 1}–{end} of {total}…")
        try:
            translated = _invoke(engine, batch, batch_context, mode)
        except TranslationError:
            raise
        except Exception as exc:
            raise TranslationFailedError(f"Translation failed. {exc}") from exc
        if len(translated) != len(batch) or any(not isinstance(item, str) for item in translated):
            raise TranslationFailedError("The translation engine returned an unexpected result.")
        translations.extend(translated)

    _stop_if_requested(should_stop)
    return TranslationResult(
        source_text=text,
        text=render_document(segments, translations),
        engine_name=engine.name,
        translated_segment_count=total,
        passthrough_count=passthrough_count,
    )


def _translate_grouped(
    segments: list[Segment],
    engine: TranslationEngine,
    progress: ProgressCallback | None,
    should_stop: StopCallback | None,
) -> str:
    """Translate paragraph groups and rebuild the original line order."""
    texts = [segment.original for segment in segments]
    flags = [segment.needs_translation for segment in segments]
    max_chars = int(getattr(engine, "max_chunk_chars", 4000) or 4000)
    overlap = int(getattr(engine, "overlap_lines", 2) or 0)
    planned = plan_chunks(texts, flags, max_chars=max_chars, overlap_lines=overlap)
    output = list(texts)
    translated_chunks = [chunk for chunk in planned if chunk.translate]
    for number, chunk in enumerate(translated_chunks, start=1):
        _stop_if_requested(should_stop)
        first = chunk.indexes[0] + 1
        last = chunk.indexes[-1] + 1
        _report(progress, f"Translating lines {first}–{last} ({number} of {len(translated_chunks)})…")
        context = [texts[index] for index in chunk.context_indexes]
        source = [texts[index] for index in chunk.indexes]
        try:
            produced = _call_chunk(engine, source, context, should_stop)
        except TranslationError:
            raise
        except Exception as exc:
            raise TranslationFailedError(f"Translation failed. {exc}") from exc
        if len(produced) != len(source):
            raise TranslationFailedError(
                "The translation did not return the same number of lines, so the "
                "document was not changed. Speaker names were left as written."
            )
        for index, source_line, translated in zip(chunk.indexes, source, produced, strict=True):
            if not flags[index]:
                output[index] = source_line
            else:
                output[index] = with_original_speaker(source_line, translated)
    return "\n".join(output)


def _call_chunk(
    engine: TranslationEngine,
    source: list[str],
    context: list[str],
    should_stop: StopCallback | None,
) -> list[str]:
    """Pass the cancel check when the engine accepts it."""
    method = engine.translate_chunk
    if "should_stop" in inspect.signature(method).parameters:
        return method(source, context, should_stop=should_stop)
    return method(source, context)


def _pending_contexts(segments: list[Segment]) -> list[str]:
    """Previous Urdu utterance for each line that will be translated."""
    contexts: list[str] = []
    previous = ""
    for segment in segments:
        if not segment.needs_translation:
            continue
        contexts.append(previous)
        previous = segment.source_for_engine()
    return contexts


def _invoke(engine: TranslationEngine, batch: list[str], contexts: list[str] | None, mode: str) -> list[str]:
    if mode == "contextual" and contexts is not None:
        method = getattr(engine, "translate_in_context", None)
        if method is not None:
            return method(batch, contexts)
    return engine.translate_batch(batch)


def _prefixed(progress: ProgressCallback | None, label: str) -> ProgressCallback | None:
    if progress is None:
        return None

    def report(message: str) -> None:
        progress(f"{label}: {message}")

    return report


def _batch_size(engine: TranslationEngine) -> int:
    """Use the engine's preferred batch size when it provides one."""
    raw = getattr(engine, "preferred_batch_size", TRANSLATION_BATCH_SIZE)
    if isinstance(raw, bool):
        return TRANSLATION_BATCH_SIZE
    try:
        size = int(raw)
    except (TypeError, ValueError):
        return TRANSLATION_BATCH_SIZE
    if size < 1:
        return TRANSLATION_BATCH_SIZE
    return size


def _report(progress: ProgressCallback | None, message: str) -> None:
    if progress is not None:
        progress(message)


def _stop_if_requested(should_stop: StopCallback | None) -> None:
    if should_stop is not None and should_stop():
        raise TranslationCancelled("Translation was cancelled.")
