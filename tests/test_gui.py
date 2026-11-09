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


def _inside(window, widget) -> bool:
    if not widget.isVisible() or widget.width() < 8 or widget.height() < 8:
        return False
    top_left = widget.mapTo(window, widget.rect().topLeft())
    bottom_right = widget.mapTo(window, widget.rect().bottomRight())
    area = window.rect()
    return (
        top_left.x() >= 0
        and top_left.y() >= 0
        and bottom_right.x() <= area.width() + 1
        and bottom_right.y() <= area.height() + 1
    )


def test_the_window_can_resize_minimize_and_maximize(qapp, tmp_path: Path):
    window = MainWindow(models_directory=tmp_path / "models", history_database=tmp_path / "history.db")
    window.show()
    qapp.processEvents()
    try:
        flags = window.windowFlags()
        assert flags & Qt.WindowType.WindowMinimizeButtonHint
        assert flags & Qt.WindowType.WindowMaximizeButtonHint
        assert flags & Qt.WindowType.WindowCloseButtonHint
        assert flags & Qt.WindowType.WindowSystemMenuHint
        assert not flags & Qt.WindowType.FramelessWindowHint
        assert window.minimumWidth() <= 960
        assert 560 <= window.minimumHeight() <= 780
        assert window.maximumWidth() > 2000
        assert window.maximumHeight() > 2000

        window.showNormal()
        window.resize(1000, window.minimumHeight())
        window.move(40, 30)
        qapp.processEvents()
        assert window.width() == 1000
        assert window.height() == window.minimumHeight()

        window.resize(1400, 900)
        qapp.processEvents()
        assert window.width() == 1400
        assert window.height() == 900

        window.showMinimized()
        qapp.processEvents()
        assert window.isMinimized()
        window.showNormal()
        qapp.processEvents()
        assert not window.isMinimized()
        assert window.width() == 1400
        assert window.height() == 900

        window.resize(1000, window.minimumHeight())
        window.move(40, 30)
        qapp.processEvents()
        previous = window.geometry()
        window.showMaximized()
        qapp.processEvents()
        assert window.isMaximized()
        window.showNormal()
        qapp.processEvents()
        assert not window.isMaximized()
        restored = window.geometry()
        assert abs(restored.width() - previous.width()) <= 4
        assert abs(restored.height() - previous.height()) <= 4
        assert abs(restored.x() - previous.x()) <= 4
        assert abs(restored.y() - previous.y()) <= 4

        window.move(-5000, -5000)
        window._clamp_to_available_screen()
        area = window.screen().availableGeometry()
        assert window.x() >= area.left()
        assert window.y() >= area.top()
    finally:
        window.showNormal()
        window.close()


def test_translate_and_clear_stay_under_the_urdu_panel(qapp, tmp_path: Path):
    window = MainWindow(models_directory=tmp_path / "models", history_database=tmp_path / "history.db")
    window.show()
    qapp.processEvents()
    try:
        assert window.translate_button.objectName() == "PrimaryButton"
        assert window.translate_button.text() == "Translate"
        window._confirm = lambda _message: True
        for width, height in ((900, 620), (1500, 980)):
            window.resize(width, height)
            qapp.processEvents()
            assert _inside(window, window.translate_button)
            assert _inside(window, window.clear_button)
            assert _inside(window, window.copy_translation_button)
            assert _inside(window, window.export_translation_button)
            assert _inside(window, window.copy_gist_button)
            assert _inside(window, window.export_gist_button)
            assert _inside(window, window.gist_editor)
            assert _inside(window, window.regenerate_summary_button)
            translate_top = window.translate_button.mapTo(window, window.translate_button.rect().topLeft()).y()
            urdu_bottom = window.urdu_editor.mapTo(window, window.urdu_editor.rect().bottomLeft()).y()
            assert translate_top > urdu_bottom
            english_bottom = window.english_editor.mapTo(window, window.english_editor.rect().bottomLeft()).y()
            export_top = window.copy_translation_button.mapTo(
                window, window.copy_translation_button.rect().topLeft()
            ).y()
            assert export_top > english_bottom

        window.urdu_editor.setPlainText("سلام")
        window.english_editor.setPlainText("Hello")
        window.clear_button.click()
        assert window.urdu_editor.toPlainText() == ""
        assert window.english_editor.toPlainText() == ""
        assert window.translate_button.isEnabled() is False
        window.urdu_editor.setPlainText("سلام")
        assert window.translate_button.isEnabled()
        window.translate_button.click()
        assert window.translate_button.text() == "Translating…"
        _wait_until(qapp, lambda: not window._busy)
    finally:
        window.close()


def test_window_size_and_maximized_state_are_restored(qapp, tmp_path: Path, monkeypatch):
    monkeypatch.setenv("URDU_TRANSLATOR_DATA", str(tmp_path))
    first = MainWindow(models_directory=tmp_path / "models", history_database=tmp_path / "history.db")
    first.show()
    qapp.processEvents()
    try:
        first.showNormal()
        first.resize(1024, 700)
        first.move(48, 36)
        qapp.processEvents()
        area = first.screen().availableGeometry()
    finally:
        first.close()

    second = MainWindow(models_directory=tmp_path / "models", history_database=tmp_path / "history.db")
    second.show()
    qapp.processEvents()
    try:
        expected_width = max(min(1024, area.width()), second.minimumWidth())
        expected_height = max(min(700, area.height()), second.minimumHeight())
        assert abs(second.width() - expected_width) <= 4
        assert abs(second.height() - expected_height) <= 4
        assert second.x() >= area.left()
        assert second.y() >= area.top()
        assert second.x() + 80 <= area.right()
        assert second.y() + 40 <= area.bottom()
        second.showMaximized()
        qapp.processEvents()
        assert second.isMaximized()
    finally:
        second.close()

    third = MainWindow(models_directory=tmp_path / "models", history_database=tmp_path / "history.db")
    third.show()
    qapp.processEvents()
    try:
        assert third.isMaximized()
        third.showNormal()
        qapp.processEvents()
        assert not third.isMaximized()
    finally:
        third.close()
