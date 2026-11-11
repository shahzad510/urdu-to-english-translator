"""Both editors use a fixed black-on-white appearance."""

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from urdu_translator.gui.appearance import (
    EDITOR_BACKGROUND,
    EDITOR_PLACEHOLDER,
    EDITOR_SELECTION,
    EDITOR_SELECTION_TEXT,
    EDITOR_TEXT,
    stylesheet,
)


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    application = QApplication.instance()
    if application is None:
        application = QApplication([])
    return application


def test_stylesheet_keeps_the_window_chrome_and_white_panels():
    text = stylesheet()
    assert "#D0D0D0" in text
    assert "#34495E" in text
    assert "#C9A45C" in text
    assert "#F4F5F6" in text
    assert "#202020" in text
    assert "QFrame#Panel, QFrame#EnglishPanel, QFrame#GistPanel" in text
    hover = _rule(text, "QPushButton:hover")
    pressed = _rule(text, "QPushButton:pressed")
    selected = _rule(text, "QRadioButton:checked")
    assert "#E6EEF5" in hover
    assert "#C9A45C" not in hover
    assert "#D5E0EA" in pressed
    assert "#D6E4F0" in selected
    assert "#1A3654" in selected
    primary = _rule(text, "QPushButton#PrimaryButton")
    primary_hover = _rule(text, "QPushButton#PrimaryButton:hover")
    assert "#34495E" in primary
    assert "#FFFFFF" in primary
    assert "#3E5670" in primary_hover
    assert "#FFFFFF" in _rule(text, "QFrame#Panel, QFrame#EnglishPanel, QFrame#GistPanel")
    assert "__" not in text
    assert "AppearanceDialog" not in text
    assert "ColourCard" not in text
    assert "PreviewUrdu" not in text
    assert "PreviewEnglish" not in text


def test_editors_are_black_on_white(qapp, tmp_path: Path):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QPalette
    from PySide6.QtWidgets import QPushButton

    from urdu_translator.gui.main_window import MainWindow

    window = MainWindow(models_directory=tmp_path / "models", history_database=tmp_path / "history.db")
    window.show()
    qapp.processEvents()
    try:
        labels = [button.text() for button in window.findChildren(QPushButton)]
        assert "Colour" not in labels
        assert not hasattr(window, "urdu_colour_button")
        assert not hasattr(window, "english_colour_button")

        assert window.urdu_editor.layoutDirection() == Qt.LayoutDirection.RightToLeft
        assert window.urdu_editor.document().defaultTextOption().textDirection() == Qt.LayoutDirection.LeftToRight
        assert window.english_editor.layoutDirection() == Qt.LayoutDirection.LeftToRight
        assert window.english_editor.document().defaultTextOption().textDirection() == Qt.LayoutDirection.LeftToRight

        window.urdu_editor.setPlainText("سلام")
        window.english_editor.setPlainText("Hello")
        qapp.processEvents()

        for editor in (window.urdu_editor, window.english_editor):
            text, background = _editor_colors(editor)
            assert text == EDITOR_TEXT
            assert background == EDITOR_BACKGROUND
            assert _rendered_background(editor) == EDITOR_BACKGROUND
            sheet = editor.styleSheet().replace(" ", "")
            assert f"color:{EDITOR_TEXT}" in sheet
            assert f"background-color:{EDITOR_BACKGROUND}" in sheet
            assert f"selection-background-color:{EDITOR_SELECTION}" in sheet
            assert f"selection-color:{EDITOR_SELECTION_TEXT}" in sheet
            viewport = editor.viewport()
            assert viewport.autoFillBackground()
            highlight = viewport.palette().color(QPalette.ColorRole.Highlight).name().upper()
            highlighted = viewport.palette().color(QPalette.ColorRole.HighlightedText).name().upper()
            placeholder = viewport.palette().color(QPalette.ColorRole.PlaceholderText).name().upper()
            assert highlight == EDITOR_SELECTION
            assert highlighted == EDITOR_SELECTION_TEXT
            assert placeholder == EDITOR_PLACEHOLDER
            assert _contrast(placeholder, EDITOR_BACKGROUND) >= 4.5
    finally:
        window.close()


def test_colour_settings_are_gone():
    root = Path(__file__).resolve().parents[1]
    gui = root / "urdu_translator" / "gui"
    assert not (gui / "appearance_dialog.py").exists()
    sources = "\n".join(path.read_text(encoding="utf-8") for path in gui.glob("*.py"))
    for obsolete in (
        "AppearanceDialog",
        "load_appearance",
        "save_appearance",
        "literal/foreground",
        "contextual/background",
        "choose_colours",
        "ColourCard",
    ):
        assert obsolete not in sources


def _editor_colors(editor) -> tuple[str, str]:
    from PySide6.QtGui import QPalette

    text = editor.viewport().palette().color(QPalette.ColorRole.Text).name().upper()
    background = editor.viewport().palette().color(QPalette.ColorRole.Base).name().upper()
    assert editor.palette().color(QPalette.ColorRole.Text).name().upper() == text
    assert editor.palette().color(QPalette.ColorRole.Base).name().upper() == background
    return text, background


def _rendered_background(editor) -> str:
    from PySide6.QtGui import QImage

    editor.resize(240, 140)
    image = QImage(editor.size(), QImage.Format.Format_ARGB32)
    editor.render(image)
    counts: dict[str, int] = {}
    width = image.width()
    height = image.height()
    for y in range(4, max(height - 4, 5), 3):
        for x in range(4, max(width - 4, 5), 3):
            color = image.pixelColor(x, y).name().upper()
            counts[color] = counts.get(color, 0) + 1
    return max(counts, key=counts.get)


def _rule(sheet: str, selector: str) -> str:
    marker = selector + " {"
    start = sheet.index(marker) + len(marker)
    return sheet[start:sheet.index("}", start)]


def _contrast(foreground: str, background: str) -> float:
    lighter = max(_luminance(foreground), _luminance(background))
    darker = min(_luminance(foreground), _luminance(background))
    return (lighter + 0.05) / (darker + 0.05)


def _luminance(color: str) -> float:
    channels = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]

    def channel(value: float) -> float:
        if value <= 0.04045:
            return value / 12.92
        return ((value + 0.055) / 1.055) ** 2.4

    red, green, blue = (channel(value) for value in channels)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue
