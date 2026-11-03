"""Background translation so the window stays responsive."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from urdu_translator.errors import AppError, TranslationCancelled
from urdu_translator.translation.loader import load_engine
from urdu_translator.translation.service import translate_document

logger = logging.getLogger("urdu_translator.worker")


class TranslateWorker(QThread):
    """Run :func:`translate_document` off the window thread.

    Signals carry status text and the finished result. The worker does not
    touch widgets or the history database.
    """

    succeeded = Signal(object)
    failed = Signal(str)
    cancelled = Signal()
    status_message = Signal(str)

    def __init__(self, text: str, models_dir: Path) -> None:
        super().__init__()
        self._text = text
        self._models_dir = Path(models_dir)

    def run(self) -> None:
        try:
            result = translate_document(
                self._text,
                lambda: load_engine(self._models_dir),
                progress=self.status_message.emit,
                should_stop=self.isInterruptionRequested,
            )
        except TranslationCancelled:
            self.cancelled.emit()
        except AppError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            logger.error("Unexpected translation error (%s): %s", type(exc).__name__, exc)
            self.failed.emit(
                "Translation failed because of an unexpected error. "
                "The Urdu text was not written to the log."
            )
        else:
            self.succeeded.emit(result)
