"""Colour choices for the Urdu, literal, and contextual panels."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QColorDialog,
)

from urdu_translator.gui.appearance import (
    DEFAULT_APPEARANCE,
    Appearance,
    PanelColors,
    contrast_problems,
    contrast_ratio,
    stylesheet,
    swatch_style,
    with_panel,
)
from urdu_translator.gui.editors import configure_editor
from urdu_translator.gui.fonts import interface_font, urdu_font

_PANELS = (
    ("urdu", "Urdu", "PreviewUrdu", "السلام علیکم، آپ کیسے ہیں؟"),
    ("literal", "Literal English", "PreviewLiteral", "Peace be upon you, how are you?"),
    ("contextual", "Contextual English", "PreviewContextual", "Hello, how are you?"),
)


class AppearanceDialog(QDialog):
    """Pick text and background colours, with a preview that updates immediately."""

    def __init__(self, appearance: Appearance, parent=None, on_change=None) -> None:
        super().__init__(parent)
        self.setObjectName("AppearanceDialog")
        self.setWindowTitle("Text colours")
        self.resize(640, 560)
        self._appearance = appearance
        self._on_change = on_change
        self._previews: dict[str, QPlainTextEdit] = {}
        self._text_buttons: dict[str, QPushButton] = {}
        self._background_buttons: dict[str, QPushButton] = {}
        self._notes: dict[str, QLabel] = {}
        self._build()
        self._refresh()

    def appearance(self) -> Appearance:
        """Colours currently shown in the dialog."""
        return self._appearance

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        title = QLabel("Text colours")
        title.setObjectName("Title")
        layout.addWidget(title)
        note = QLabel("Each panel keeps its own text and background colour. The preview uses the same colours as the window.")
        note.setObjectName("Subtitle")
        note.setWordWrap(True)
        layout.addWidget(note)

        for key, label, frame_name, sample in _PANELS:
            layout.addWidget(self._panel_block(key, label, frame_name, sample))

        self.summary = QLabel()
        self.summary.setObjectName("ContrastNote")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        buttons = QHBoxLayout()
        reset = QPushButton("Reset to default")
        reset.clicked.connect(self._reset)
        self.save_button = QPushButton("Save")
        self.save_button.setObjectName("PrimaryButton")
        self.save_button.clicked.connect(self.accept)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(reset)
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(self.save_button)
        layout.addLayout(buttons)

    def _panel_block(self, key: str, label: str, frame_name: str, sample: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName(frame_name)
        outer = QVBoxLayout(frame)
        outer.setContentsMargins(12, 10, 12, 10)
        heading = QHBoxLayout()
        title = QLabel(label)
        title.setObjectName("PanelTitle")
        heading.addWidget(title)
        heading.addStretch(1)
        text_button = QPushButton("Text")
        text_button.setObjectName("SwatchButton")
        text_button.clicked.connect(lambda _checked=False, panel=key: self._pick(panel, "foreground"))
        background_button = QPushButton("Background")
        background_button.setObjectName("SwatchButton")
        background_button.clicked.connect(lambda _checked=False, panel=key: self._pick(panel, "background"))
        heading.addWidget(text_button)
        heading.addWidget(background_button)
        outer.addLayout(heading)

        preview = QPlainTextEdit()
        if key == "urdu":
            configure_editor(
                preview,
                font=urdu_font(16),
                direction=Qt.LayoutDirection.RightToLeft,
                text_direction=Qt.LayoutDirection.LeftToRight,
                alignment=Qt.AlignmentFlag.AlignRight,
                placeholder="",
            )
        else:
            configure_editor(
                preview,
                font=interface_font(13),
                direction=Qt.LayoutDirection.LeftToRight,
                alignment=Qt.AlignmentFlag.AlignLeft,
                placeholder="",
            )
        preview.setPlainText(sample)
        preview.setReadOnly(True)
        preview.setFixedHeight(72)
        outer.addWidget(preview)
        contrast = QLabel()
        contrast.setObjectName("ContrastNote")
        outer.addWidget(contrast)
        self._previews[key] = preview
        self._text_buttons[key] = text_button
        self._background_buttons[key] = background_button
        self._notes[key] = contrast
        return frame

    def _pick(self, panel: str, field: str) -> None:
        colors = _colors_for(self._appearance, panel)
        current = colors.foreground if field == "foreground" else colors.background
        chosen = QColorDialog.getColor(QColor(current), self, f"{panel} {field}")
        if not chosen.isValid():
            return
        updated = PanelColors(
            chosen.name().upper() if field == "foreground" else colors.foreground,
            chosen.name().upper() if field == "background" else colors.background,
        )
        self._appearance = with_panel(self._appearance, panel, updated)
        self._refresh()

    def _reset(self) -> None:
        self._appearance = DEFAULT_APPEARANCE
        self._refresh()

    def _refresh(self) -> None:
        self.setStyleSheet(stylesheet(self._appearance))
        for key, _label, _frame, _sample in _PANELS:
            colors = _colors_for(self._appearance, key)
            self._text_buttons[key].setStyleSheet(swatch_style(colors.foreground))
            self._background_buttons[key].setStyleSheet(swatch_style(colors.background))
            ratio = contrast_ratio(colors.foreground, colors.background)
            self._notes[key].setText(f"Contrast {ratio:.2f}:1")
        problems = contrast_problems(self._appearance)
        self.summary.setText(" ".join(problems))
        self.save_button.setEnabled(not problems)
        if self._on_change is not None and not problems:
            self._on_change(self._appearance)


def _colors_for(appearance: Appearance, panel: str) -> PanelColors:
    if panel == "urdu":
        return appearance.urdu
    if panel == "literal":
        return appearance.literal
    return appearance.contextual
