"""Colours for the translator window.

Every colour the window paints comes from this module. Widgets do not
choose their own colours. Preferences are stored with Qt settings, which
uses the registry on Windows and a config file on Ubuntu.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from PySide6.QtCore import QSettings

MIN_CONTRAST = 4.5

_TEMPLATE = """
QMainWindow, QDialog#HistoryDialog, QDialog#AppearanceDialog {
    background: __CHROME__;
    color: __INK__;
}
QWidget#Root, QDialog#HistoryDialog, QDialog#AppearanceDialog {
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
QFrame#Panel {
    background: __URDU_BG__;
    border: 1px solid __BORDER__;
    border-radius: 16px;
}
QFrame#Panel QPlainTextEdit {
    color: __URDU_FG__;
    background: __URDU_BG__;
    border: none;
    selection-background-color: __ACCENT__;
    selection-color: __SELECTION_INK__;
}
QFrame#EnglishPanel {
    background: __LITERAL_BG__;
    border: 1px solid __BORDER__;
    border-radius: 16px;
}
QFrame#EnglishPanel QPlainTextEdit {
    color: __LITERAL_FG__;
    background: __LITERAL_BG__;
    border: none;
    selection-background-color: __ACCENT__;
    selection-color: __SELECTION_INK__;
}
QFrame#ContextualPanel {
    background: __CONTEXT_BG__;
    border: 1px solid __BORDER__;
    border-radius: 16px;
}
QFrame#ContextualPanel QPlainTextEdit {
    color: __CONTEXT_FG__;
    background: __CONTEXT_BG__;
    border: none;
    selection-background-color: __ACCENT__;
    selection-color: __SELECTION_INK__;
}
QFrame#PreviewUrdu {
    background: __URDU_BG__;
    border: 1px solid __BORDER__;
    border-radius: 12px;
}
QFrame#PreviewUrdu QPlainTextEdit {
    color: __URDU_FG__;
    background: __URDU_BG__;
    border: none;
}
QFrame#PreviewLiteral {
    background: __LITERAL_BG__;
    border: 1px solid __BORDER__;
    border-radius: 12px;
}
QFrame#PreviewLiteral QPlainTextEdit {
    color: __LITERAL_FG__;
    background: __LITERAL_BG__;
    border: none;
}
QFrame#PreviewContextual {
    background: __CONTEXT_BG__;
    border: 1px solid __BORDER__;
    border-radius: 12px;
}
QFrame#PreviewContextual QPlainTextEdit {
    color: __CONTEXT_FG__;
    background: __CONTEXT_BG__;
    border: none;
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
    background: transparent;
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
QPushButton#SwatchButton {
    border: 1px solid __BORDER__;
    border-radius: 8px;
    padding: 6px 10px;
    min-width: 88px;
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
    background: __URDU_BG__;
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
QLabel#EmptyHistory, QLabel#ContrastNote {
    color: __MUTED__;
    background: transparent;
    font-size: 14px;
}
"""


@dataclass(frozen=True)
class PanelColors:
    """Foreground and background for one text panel."""

    foreground: str
    background: str


@dataclass(frozen=True)
class Appearance:
    """The colours the window is allowed to use."""

    urdu: PanelColors
    literal: PanelColors
    contextual: PanelColors
    border: str = "#D0D0D0"
    button: str = "#34495E"
    accent: str = "#C9A45C"
    chrome: str = "#F4F5F6"


DEFAULT_APPEARANCE = Appearance(
    urdu=PanelColors("#202020", "#FFFFFF"),
    literal=PanelColors("#202020", "#FFFFFF"),
    contextual=PanelColors("#202020", "#FFFFFF"),
)


def contrast_ratio(foreground: str, background: str) -> float:
    """WCAG contrast ratio between two ``#RRGGBB`` colours."""
    lighter = max(_luminance(foreground), _luminance(background))
    darker = min(_luminance(foreground), _luminance(background))
    return (lighter + 0.05) / (darker + 0.05)


def contrast_problems(appearance: Appearance) -> list[str]:
    """Names of panels whose text is hard to read on their background."""
    problems: list[str] = []
    pairs = (
        ("Urdu", appearance.urdu),
        ("Literal English", appearance.literal),
        ("Contextual English", appearance.contextual),
    )
    for label, panel in pairs:
        ratio = contrast_ratio(panel.foreground, panel.background)
        if ratio < MIN_CONTRAST:
            problems.append(
                f"{label} contrast is {ratio:.2f}:1. Text needs at least {MIN_CONTRAST:.1f}:1."
            )
    return problems


def stylesheet(appearance: Appearance) -> str:
    """Qt stylesheet for ``appearance``. Layout direction is not set here."""
    button_text = ink_on(appearance.button)
    selection_ink = ink_on(appearance.accent)
    muted = _muted(appearance.chrome)
    replacements = {
        "__CHROME__": appearance.chrome,
        "__INK__": appearance.urdu.foreground,
        "__MUTED__": muted,
        "__BORDER__": appearance.border,
        "__BUTTON__": appearance.button,
        "__BUTTON_TEXT__": button_text,
        "__ACCENT__": appearance.accent,
        "__SELECTION_INK__": selection_ink,
        "__URDU_FG__": appearance.urdu.foreground,
        "__URDU_BG__": appearance.urdu.background,
        "__LITERAL_FG__": appearance.literal.foreground,
        "__LITERAL_BG__": appearance.literal.background,
        "__CONTEXT_FG__": appearance.contextual.foreground,
        "__CONTEXT_BG__": appearance.contextual.background,
    }
    text = _TEMPLATE
    for token, value in replacements.items():
        text = text.replace(token, value)
    return text


def swatch_style(color: str) -> str:
    """Style for a colour-picker button. The colour is the button background."""
    ink = ink_on(color)
    return (
        "QPushButton#SwatchButton {"
        f"background: {color}; color: {ink}; border: 1px solid #D0D0D0;"
        "border-radius: 8px; padding: 6px 10px; min-width: 88px;"
        "}"
    )


def ink_on(background: str) -> str:
    """White or near-black text, whichever is readable on ``background``."""
    white = contrast_ratio("#FFFFFF", background)
    dark = contrast_ratio("#202020", background)
    return "#FFFFFF" if white >= dark else "#202020"


def load_appearance(path: Path | None = None) -> Appearance:
    """Read saved panel colours. Missing or invalid values stay at the defaults."""
    settings = _settings(path)
    return Appearance(
        urdu=_load_panel(settings, "urdu", DEFAULT_APPEARANCE.urdu),
        literal=_load_panel(settings, "literal", DEFAULT_APPEARANCE.literal),
        contextual=_load_panel(settings, "contextual", DEFAULT_APPEARANCE.contextual),
    )


def save_appearance(appearance: Appearance, path: Path | None = None) -> None:
    """Store the three panel colours. Chrome colours stay at the theme defaults."""
    settings = _settings(path)
    _save_panel(settings, "urdu", appearance.urdu)
    _save_panel(settings, "literal", appearance.literal)
    _save_panel(settings, "contextual", appearance.contextual)
    settings.sync()


def with_panel(appearance: Appearance, panel: str, colors: PanelColors) -> Appearance:
    """Return a copy with one panel recoloured."""
    if panel == "urdu":
        return replace(appearance, urdu=colors)
    if panel == "literal":
        return replace(appearance, literal=colors)
    if panel == "contextual":
        return replace(appearance, contextual=colors)
    raise ValueError(f"Unknown panel {panel}.")


def normalize_color(value: str) -> str:
    """Return ``#RRGGBB`` or raise ``ValueError``."""
    text = value.strip()
    if text.startswith("#"):
        text = text[1:]
    if len(text) == 3:
        text = "".join(character * 2 for character in text)
    if len(text) != 6 or any(character not in "0123456789abcdefABCDEF" for character in text):
        raise ValueError(f"Colour {value!r} must be a hex value such as #202020.")
    return f"#{text.upper()}"


def _load_panel(settings: QSettings, name: str, default: PanelColors) -> PanelColors:
    foreground = _stored_color(settings.value(f"{name}/foreground"), default.foreground)
    background = _stored_color(settings.value(f"{name}/background"), default.background)
    return PanelColors(foreground, background)


def _save_panel(settings: QSettings, name: str, colors: PanelColors) -> None:
    settings.setValue(f"{name}/foreground", normalize_color(colors.foreground))
    settings.setValue(f"{name}/background", normalize_color(colors.background))


def _stored_color(value: object, default: str) -> str:
    if not isinstance(value, str):
        return default
    try:
        return normalize_color(value)
    except ValueError:
        return default


def _settings(path: Path | None) -> QSettings:
    if path is None:
        return QSettings("UrduTranslator", "UrduTranslator")
    return QSettings(str(path), QSettings.Format.IniFormat)


def _luminance(color: str) -> float:
    red, green, blue = _rgb(color)
    return 0.2126 * _channel(red) + 0.7152 * _channel(green) + 0.0722 * _channel(blue)


def _rgb(color: str) -> tuple[int, int, int]:
    normalized = normalize_color(color)
    return int(normalized[1:3], 16), int(normalized[3:5], 16), int(normalized[5:7], 16)


def _channel(value: int) -> float:
    channel = value / 255
    if channel <= 0.04045:
        return channel / 12.92
    return ((channel + 0.055) / 1.055) ** 2.4


def _muted(background: str) -> str:
    """A quieter label colour that still clears the contrast bar on ``background``."""
    for candidate in ("#5C656D", "#4A545C", "#3E474E", "#202020"):
        if contrast_ratio(candidate, background) >= MIN_CONTRAST:
            return candidate
    return "#202020"
