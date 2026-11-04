"""The window can be exercised without a display."""

import json
import os
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QPushButton  # noqa: E402

from urdu_translator.gui.main_window import MainWindow  # noqa: E402
from urdu_translator.translation.engine import TranslationEngine  # noqa: E402
from urdu_translator.translation.registry import register_backend, unregister_backend  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    application = QApplication.instance()
    if application is None:
        application = QApplication([])
    return application


def _wait_until(qapp, predicate, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        qapp.processEvents()
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("Timed out waiting for the window to update.")


def test_panels_use_the_expected_directions(qapp, tmp_path: Path):
    window = MainWindow(models_directory=tmp_path / "models", history_database=tmp_path / "history.db")
    window.show()
    qapp.processEvents()
    try:
        assert window.urdu_editor.layoutDirection() == Qt.LayoutDirection.RightToLeft
        assert window.english_editor.layoutDirection() == Qt.LayoutDirection.LeftToRight
        assert window.translate_button.text() == "Translate"
        assert window.clear_button.text() == "Clear"
        assert window.copy_translation_button.text() == "Copy Translation"
        assert window.save_translation_button.text() == "Save Translation as TXT"
        assert window.export_translation_button.text() == "Export Translation as DOCX"
        assert window.export_complete_button.text() == "Export Complete Document"
        assert window.copy_gist_button.text() == "Copy Gist"
        assert window.save_gist_button.text() == "Save Gist as TXT"
        assert window.export_gist_button.text() == "Export Gist as DOCX"
        assert window.model_pill.text() == "No model loaded"
        assert not hasattr(window, "contextual_editor")
        assert not hasattr(window, "copy_button")
        assert not hasattr(window, "save_button")
        assert not hasattr(window, "export_button")
        titles = [label.text() for label in window.findChildren(QLabel)]
        buttons = [button.text() for button in window.findChildren(QPushButton)]
        assert "Urdu Text" in titles
        assert "English Translation" in titles
        assert "Gist / Contextual Summary" in titles
        assert "Summary Status" in titles
        assert "Copy" not in buttons
        assert "Save TXT" not in buttons
        assert "Export DOCX" not in buttons
    finally:
        window.close()


def test_urdu_panel_types_from_the_right_without_reversing_english(qapp, tmp_path: Path):
    window = MainWindow(models_directory=tmp_path / "models", history_database=tmp_path / "history.db")
    try:
        assert window.urdu_editor.layoutDirection() == Qt.LayoutDirection.RightToLeft
        options = window.urdu_editor.document().defaultTextOption()
        assert options.textDirection() == Qt.LayoutDirection.LeftToRight
        assert options.alignment() == Qt.AlignmentFlag.AlignRight
    finally:
        window.close()


def test_missing_model_is_shown_and_history_stays_empty(qapp, tmp_path: Path):
    window = MainWindow(models_directory=tmp_path / "models", history_database=tmp_path / "history.db")
    try:
        window.urdu_editor.setPlainText("جمال :۔سلام")
        window.translate()
        assert window.translate_button.text() == "Translating…"
        _wait_until(qapp, lambda: bool(window.banner_label.text()) and not window._busy)
        assert "model" in window.banner_label.text().lower()
        assert window.english_editor.toPlainText() == ""
        assert window.history is not None
        assert window.history.list_recent() == []
    finally:
        window.close()


def test_registered_backend_translates_on_a_worker_and_saves_history(qapp, tmp_path: Path):
    class EchoEngine(TranslationEngine):
        def translate_batch(self, texts: list[str]) -> list[str]:
            return [f"[{text}]" for text in texts]

    register_backend("echo-gui", lambda package: EchoEngine(package))
    models = tmp_path / "models"
    package = models / "echo"
    package.mkdir(parents=True)
    (package / "engine.json").write_text(
        json.dumps({"name": "Echo", "backend": "echo-gui", "default": True}),
        encoding="utf-8",
    )
    window = MainWindow(models_directory=models, history_database=tmp_path / "history.db")
    try:
        assert window.model_pill.text() == "Echo"
        window.urdu_editor.setPlainText("ROC/ Area:\nA-5/ Shahrag\n\nجمال :۔سلام\n")
        window.translate()
        _wait_until(
            qapp,
            lambda: "سلام" in window.english_editor.toPlainText() and not window._busy,
        )
        assert window.english_editor.toPlainText() == "ROC/ Area:\nA-5/ Shahrag\n\nJamal: [سلام]\n"
        assert window.history is not None
        records = window.history.list_recent()
        assert len(records) == 1
        assert records[0].engine_name == "Echo"
        assert records[0].contextual_text == ""
        assert records[0].source_text.startswith("ROC/ Area:")

        window._clear_documents()
        assert window.urdu_editor.toPlainText() == ""
        assert window.english_editor.toPlainText() == ""
    finally:
        window.close()
        unregister_backend("echo-gui")


def test_english_only_passthrough_does_not_need_a_model(qapp, tmp_path: Path):
    window = MainWindow(models_directory=tmp_path / "models", history_database=tmp_path / "history.db")
    try:
        window.urdu_editor.setPlainText("Freq:\n462.225 MHz\n")
        window.translate()
        _wait_until(qapp, lambda: "462.225" in window.english_editor.toPlainText() and not window._busy)
        assert window.english_editor.toPlainText() == "Freq:\n462.225 MHz\n"
        assert window.banner.isVisible() is False
        assert window.history is not None
        assert window.history.list_recent() == []
    finally:
        window.close()


def test_opening_an_old_history_row_shows_both_saved_english_texts(qapp, tmp_path: Path):
    window = MainWindow(models_directory=tmp_path / "models", history_database=tmp_path / "history.db")
    try:
        assert window.history is not None
        record = window.history.add(
            source_text="سلام",
            translated_text="Hello",
            engine_name="OPUS-MT",
            contextual_text="Peace be upon you",
            contextual_engine="IndicTrans2",
        )
        window._load_history_record(record)
        english = window.english_editor.toPlainText()
        assert window.urdu_editor.toPlainText() == "سلام"
        assert "Hello" in english
        assert "Peace be upon you" in english
        assert "Earlier contextual translation" in english
    finally:
        window.close()
