"""Panel colours come from the shared theme and stay readable."""

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from urdu_translator.gui.appearance import (
    DEFAULT_APPEARANCE,
    MIN_CONTRAST,
    PanelColors,
    contrast_problems,
    contrast_ratio,
    load_appearance,
    save_appearance,
    stylesheet,
    with_panel,
)


def test_default_colours_meet_the_contrast_bar():
    assert contrast_ratio("#202020", "#FFFFFF") >= MIN_CONTRAST
    assert contrast_problems(DEFAULT_APPEARANCE) == []
    text = stylesheet(DEFAULT_APPEARANCE)
    assert "#202020" in text
    assert "#FFFFFF" in text
    assert "#D0D0D0" in text
    assert "#34495E" in text
    assert "#C9A45C" in text
    assert "QFrame#Panel QPlainTextEdit" in text
    assert "QFrame#EnglishPanel QPlainTextEdit" in text
    assert "QFrame#ContextualPanel QPlainTextEdit" in text


def test_low_contrast_is_rejected():
    pale = with_panel(DEFAULT_APPEARANCE, "literal", PanelColors("#F5F5F5", "#FFFFFF"))
    problems = contrast_problems(pale)
    assert any("Literal English" in problem for problem in problems)


def test_colours_persist_in_a_local_settings_file(tmp_path: Path):
    path = tmp_path / "appearance.ini"
    custom = with_panel(DEFAULT_APPEARANCE, "contextual", PanelColors("#102A43", "#F7F1E4"))
    save_appearance(custom, path)
    loaded = load_appearance(path)
    assert loaded.contextual == PanelColors("#102A43", "#F7F1E4")
    assert loaded.urdu == DEFAULT_APPEARANCE.urdu
    assert contrast_problems(loaded) == []


def test_a_bad_stored_colour_falls_back_to_the_default(tmp_path: Path):
    from PySide6.QtCore import QSettings

    path = tmp_path / "appearance.ini"
    settings = QSettings(str(path), QSettings.Format.IniFormat)
    settings.setValue("urdu/foreground", "not-a-colour")
    settings.sync()
    loaded = load_appearance(path)
    assert loaded.urdu.foreground == DEFAULT_APPEARANCE.urdu.foreground


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    application = QApplication.instance()
    if application is None:
        application = QApplication([])
    return application


def test_dialog_preview_keeps_urdu_direction_and_blocks_an_unreadable_save(qapp):
    pytest.importorskip("PySide6")
    from PySide6.QtCore import Qt

    from urdu_translator.gui.appearance_dialog import AppearanceDialog

    dialog = AppearanceDialog(DEFAULT_APPEARANCE)
    try:
        assert dialog._previews["urdu"].layoutDirection() == Qt.LayoutDirection.RightToLeft
        assert dialog._previews["urdu"].document().defaultTextOption().textDirection() == Qt.LayoutDirection.LeftToRight
        assert dialog.save_button.isEnabled()
        dialog._appearance = with_panel(dialog.appearance(), "urdu", PanelColors("#FFFFFF", "#FFFFFF"))
        dialog._refresh()
        assert dialog.save_button.isEnabled() is False
        assert "Urdu" in dialog.summary.text()
        dialog._reset()
        assert dialog.save_button.isEnabled()
        assert dialog.appearance().urdu.foreground == "#202020"
    finally:
        dialog.close()


def test_window_colours_persist_without_changing_urdu_direction(qapp, tmp_path: Path):
    from PySide6.QtCore import Qt

    from urdu_translator.gui.main_window import MainWindow

    settings = tmp_path / "appearance.ini"
    window = MainWindow(
        models_directory=tmp_path / "models",
        history_database=tmp_path / "history.db",
        settings_path=settings,
    )
    try:
        assert window.urdu_colour_button.text() == "Colour"
        assert window.literal_colour_button.text() == "Colour"
        custom = with_panel(window.appearance, "urdu", PanelColors("#102A43", "#F7F1E4"))
        window.apply_appearance(custom, persist=True)
        assert window.urdu_editor.layoutDirection() == Qt.LayoutDirection.RightToLeft
        assert window.urdu_editor.document().defaultTextOption().textDirection() == Qt.LayoutDirection.LeftToRight
        assert "#102A43" in window.styleSheet()
        assert "#F7F1E4" in window.styleSheet()
    finally:
        window.close()

    restored = MainWindow(
        models_directory=tmp_path / "models",
        history_database=tmp_path / "history.db",
        settings_path=settings,
    )
    try:
        assert restored.appearance.urdu == PanelColors("#102A43", "#F7F1E4")
        assert restored.urdu_editor.layoutDirection() == Qt.LayoutDirection.RightToLeft
    finally:
        restored.close()
