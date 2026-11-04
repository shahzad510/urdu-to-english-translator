"""Background translation so the window stays responsive."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from urdu_translator.errors import AppError, TranslationCancelled
from urdu_translator.translation.loader import load_engine
from urdu_translator.translation.service import TranslationResult, produce_document_outputs

logger = logging.getLogger("urdu_translator.worker")


class TranslateWorker(QThread):
    """Translate off the window thread, then write the contextual summary.

    The English translation is published as soon as it is assembled. Summary
    failures and cancellation do not withdraw it. The worker does not touch
    widgets or the history database.
    """

    succeeded = Signal(object)
    failed = Signal(str)
    cancelled = Signal()
    status_message = Signal(str)
    gist_started = Signal()
    gist_ready = Signal(str)
    gist_failed = Signal(str)
    gist_cancelled = Signal()

    def __init__(self, text: str, models_dir: Path) -> None:
        super().__init__()
        self._text = text
        self._models_dir = Path(models_dir)

    def run(self) -> None:
        shared: dict[str, object] = {}

        def load_once():
            if "engine" not in shared:
                shared["engine"] = load_engine(self._models_dir)
            return shared["engine"]

        published = False

        def publish(result: TranslationResult) -> None:
            nonlocal published
            published = True
            self.succeeded.emit(result)

        try:
            outputs = produce_document_outputs(
                self._text,
                load_once,
                progress=self.status_message.emit,
                should_stop=self.isInterruptionRequested,
                on_translated=publish,
                on_gist_started=self.gist_started.emit,
            )
        except TranslationCancelled:
            self.cancelled.emit()
            return
        except AppError as exc:
            self.failed.emit(str(exc))
            return
        except Exception as exc:
            logger.error("Unexpected translation error (%s): %s", type(exc).__name__, exc)
            self.failed.emit(
                "Translation failed because of an unexpected error. "
                "The Urdu text was not written to the log."
            )
            return
        if not published:
            self.succeeded.emit(outputs.translation)
        if outputs.gist_cancelled:
            self.gist_cancelled.emit()
        elif outputs.gist_error:
            self.gist_failed.emit(outputs.gist_error)
        elif outputs.gist:
            self.gist_ready.emit(outputs.gist)
