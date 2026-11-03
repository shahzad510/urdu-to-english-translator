"""Text editors for the Urdu source and the English translation."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QTextOption
from PySide6.QtWidgets import QPlainTextEdit


class Editor(QPlainTextEdit):
    """Plain-text editor that leaves Ctrl+Enter free for the Translate action."""

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt API
        ctrl = event.modifiers() & Qt.KeyboardModifier.ControlModifier
        if ctrl and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            event.ignore()
            return
        super().keyPressEvent(event)


class SourceEditor(Editor):
    """Urdu editor that can open a dropped text or Word file."""

    document_dropped = Signal(str)

    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt API
        if _document_paths(event):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt API
        paths = _document_paths(event)
        if paths:
            self.document_dropped.emit(paths[0])
            event.acceptProposedAction()
            return
        super().dropEvent(event)


def configure_editor(
    editor: QPlainTextEdit,
    *,
    font: QFont,
    direction: Qt.LayoutDirection,
    alignment: Qt.AlignmentFlag,
    placeholder: str,
    text_direction: Qt.LayoutDirection | None = None,
) -> None:
    """Apply direction, wrapping, and the default alignment for new text.

    ``direction`` is the widget direction (where the cursor rests). ``text_direction``
    is the paragraph base direction. The Urdu panel uses a right-to-left widget so
    Urdu is typed from the right, with a left-to-right base so English lines such
    as ``ROC/ Area:`` are not drawn backwards.
    """
    editor.setFont(font)
    editor.setLayoutDirection(direction)
    editor.setPlaceholderText(placeholder)
    editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
    editor.setFrameStyle(0)
    editor.setTabStopDistance(28)
    options = editor.document().defaultTextOption()
    options.setTextDirection(direction if text_direction is None else text_direction)
    options.setAlignment(alignment)
    options.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
    editor.document().setDefaultTextOption(options)


def _document_paths(event) -> list[str]:
    mime = event.mimeData()
    if mime is None or not mime.hasUrls():
        return []
    paths: list[str] = []
    for url in mime.urls():
        if not url.isLocalFile():
            continue
        local = url.toLocalFile()
        if local.lower().endswith((".txt", ".docx")):
            paths.append(local)
    return paths
