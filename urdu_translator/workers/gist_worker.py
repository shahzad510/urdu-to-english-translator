"""Background contextual summary, without translating again."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from urdu_translator.errors import AppError, TranslationCancelled
from urdu_translator.translation.loader import load_engine
from urdu_translator.translation.service import summarize_loaded_engine

logger = logging.getLogger("urdu_translator.worker")


class GistWorker(QThread):
    """Write a contextual summary from English that is already on screen.

    Loading the engine reuses the llama-server process the translator started.
    """

    ready = Signal(str)
    failed = Signal(str)
    cancelled = Signal()
    status_message = Signal(str)
    gist_started = Signal()

    def __init__(self, text: str, models_dir: Path, level: str = "brief") -> None:
        super().__init__()
        self._text = text
        self._models_dir = Path(models_dir)
        self._level = level

    def run(self) -> None:
        self.gist_started.emit()
        shared: dict[str, object] = {}

        def load_once():
            if "engine" not in shared:
                shared["engine"] = load_engine(self._models_dir)
            return shared["engine"]

        try:
            gist = summarize_loaded_engine(
                load_once,
                self._text,
                progress=self.status_message.emit,
                should_stop=self.isInterruptionRequested,
                level=self._level,
            )
        except TranslationCancelled:
            self.cancelled.emit()
        except AppError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            logger.error("Unexpected summary error (%s): %s", type(exc).__name__, exc)
            self.failed.emit(
                "The contextual summary could not be written. The English translation was kept."
            )
        else:
            self.ready.emit(gist)
