"""Fixed colours for the translator window.

The Urdu and English editors are black on white. The surrounding controls
use the same fixed chrome colours. Nothing here is stored or chosen by the user.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette

_TEMPLATE = """
QMainWindow, QDialog#HistoryDialog {
    background: __CHROME__;
    color: __INK__;
}
QWidget#Root, QDialog#HistoryDialog {
    background: __CHROME__;
    color: __INK__;
    font-size: 13px;
}
QLabel#Title {
    font-size: 22px;
    font-weight: 600;
    color: __BUTTON__;
    background: transparent;
}
QLabel#Subtitle, QLabel#PanelCaption, QLabel#CountLabel {
    color: __MUTED__;
    background: transparent;
}
QLabel#PanelTitle {
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 0.4px;
    color: __BUTTON__;
    background: transparent;
}
QFrame#Panel, QFrame#EnglishPanel, QFrame#GistPanel {
    background: #FFFFFF;
    border: 1px solid __BORDER__;
    border-radius: 16px;
}
QFrame#ErrorBanner {
    background: #f8e6df;
    border: 1px solid #e3c2b8;
    border-radius: 12px;
}
QFrame#ErrorBanner[kind="warning"] {
    background: #f8efdc;
    border: 1px solid #e4d2ae;
}
QFrame#ErrorBanner[kind="info"] {
    background: #e4eee9;
    border: 1px solid #c5d7ce;
}
QLabel#BannerText {
    background: transparent;
    color: #4a332c;
}
QFrame#ErrorBanner[kind="info"] QLabel#BannerText {
    color: __BUTTON__;
}
QFrame#ErrorBanner[kind="warning"] QLabel#BannerText {
    color: #5c4318;
}
QPlainTextEdit {
    border: none;
    selection-background-color: __ACCENT__;
    selection-color: __SELECTION_INK__;
}
QPushButton {
    background: __CHROME__;
    color: __BUTTON__;
    border: 1px solid __BORDER__;
    border-radius: 10px;
    padding: 8px 14px;
    min-height: 20px;
}
QPushButton:hover {
    background: __ACCENT__;
    color: __SELECTION_INK__;
    border-color: __ACCENT__;
}
QPushButton:disabled {
    color: __MUTED__;
    border-color: __BORDER__;
    background: __CHROME__;
}
QPushButton#PrimaryButton {
    background: __BUTTON__;
    color: __BUTTON_TEXT__;
    border: none;
    font-weight: 600;
    padding: 8px 18px;
}
QPushButton#PrimaryButton:hover {
    background: __BUTTON__;
    color: __BUTTON_TEXT__;
    border: none;
}
QPushButton#PrimaryButton:disabled {
    background: __BORDER__;
    color: __CHROME__;
}
QPushButton#ModelPill {
    border-radius: 12px;
    padding: 5px 12px;
    font-weight: 600;
}
QPushButton#ModelPill[state="missing"] {
    background: #f3e6d4;
    color: #6a4b24;
    border: 1px solid #e4d2ae;
}
QPushButton#ModelPill[state="ready"] {
    background: #dce8e2;
    color: __BUTTON__;
    border: 1px solid #c5d7ce;
}
QPushButton#ModelPill[state="unsupported"],
QPushButton#ModelPill[state="invalid"] {
    background: #f6ddd6;
    color: #6f2d22;
    border: 1px solid #e3c2b8;
}
QPushButton#QuietButton {
    border: none;
    padding: 4px 8px;
    color: #6f2d22;
    background: transparent;
}
QPushButton#QuietButton:hover {
    background: rgba(111, 45, 34, 0.08);
    color: #6f2d22;
    border: none;
}
QSplitter::handle {
    background: __BORDER__;
    margin: 24px 4px;
}
QStatusBar {
    background: __CHROME__;
    color: __MUTED__;
}
QProgressBar {
    border: none;
    background: __BORDER__;
    border-radius: 3px;
    max-height: 6px;
}
QProgressBar::chunk {
    background: __ACCENT__;
    border-radius: 3px;
}
QTableWidget {
    background: #FFFFFF;
    alternate-background-color: __CHROME__;
    color: __INK__;
    border: 1px solid __BORDER__;
    border-radius: 10px;
    gridline-color: __BORDER__;
    selection-background-color: __ACCENT__;
    selection-color: __SELECTION_INK__;
}
QHeaderView::section {
    background: __CHROME__;
    color: __MUTED__;
    border: none;
    border-bottom: 1px solid __BORDER__;
    padding: 8px;
    font-weight: 600;
}
QLabel#EmptyHistory {
    color: __MUTED__;
    background: transparent;
    font-size: 14px;
}
"""



EDITOR_TEXT = "#000000"
EDITOR_BACKGROUND = "#FFFFFF"
EDITOR_SELECTION = "#0000FF"
EDITOR_SELECTION_TEXT = "#FFFFFF"
EDITOR_PLACEHOLDER = "#595959"

_CHROME = "#F4F5F6"
_INK = "#202020"
_MUTED = "#5C656D"
_BORDER = "#D0D0D0"
_BUTTON = "#34495E"
_BUTTON_TEXT = "#FFFFFF"
_ACCENT = "#C9A45C"
_SELECTION_INK = "#202020"


def stylesheet() -> str:
    """Qt stylesheet for the window chrome. Editor text colour is applied separately."""
    replacements = {
        "__CHROME__": _CHROME,
        "__INK__": _INK,
        "__MUTED__": _MUTED,
        "__BORDER__": _BORDER,
        "__BUTTON__": _BUTTON,
        "__BUTTON_TEXT__": _BUTTON_TEXT,
        "__ACCENT__": _ACCENT,
        "__SELECTION_INK__": _SELECTION_INK,
    }
    text = _TEMPLATE
    for token, value in replacements.items():
        text = text.replace(token, value)
    return text


def apply_editor_colors(editor) -> None:
    """Paint one text editor and the viewport where its text is drawn.

    Both editors use black text on white. The window stylesheet does not paint
    the editor's text area, so the colour is set on the editor itself and on
    the viewport palette used for typed text, placeholders, and loaded text.
    """
    foreground = QColor(EDITOR_TEXT)
    background = QColor(EDITOR_BACKGROUND)
    highlight = QColor(EDITOR_SELECTION)
    highlighted = QColor(EDITOR_SELECTION_TEXT)
    placeholder = QColor(EDITOR_PLACEHOLDER)
    editor.setStyleSheet(
        "QPlainTextEdit {"
        f"color: {EDITOR_TEXT};"
        f"background-color: {EDITOR_BACKGROUND};"
        f"selection-background-color: {EDITOR_SELECTION};"
        f"selection-color: {EDITOR_SELECTION_TEXT};"
        "border: none;"
        "}"
    )
    for widget in (editor, editor.viewport()):
        palette = widget.palette()
        palette.setColor(QPalette.ColorRole.Text, foreground)
        palette.setColor(QPalette.ColorRole.WindowText, foreground)
        palette.setColor(QPalette.ColorRole.Base, background)
        palette.setColor(QPalette.ColorRole.Window, background)
        palette.setColor(QPalette.ColorRole.Highlight, highlight)
        palette.setColor(QPalette.ColorRole.HighlightedText, highlighted)
        palette.setColor(QPalette.ColorRole.PlaceholderText, placeholder)
        widget.setPalette(palette)
    editor.viewport().setAutoFillBackground(True)
    editor.viewport().update()
    editor.update()
