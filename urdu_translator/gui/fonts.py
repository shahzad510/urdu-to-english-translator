"""Fonts and the application icon."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPixmap

from urdu_translator.paths import fonts_dir

_preferred_urdu_family: str | None = None

_URDU_FALLBACKS = (
    "Noto Nastaliq Urdu",
    "Noto Naskh Arabic",
    "KacstNaskh",
    "FreeSerif",
    "Segoe UI",
)
_INTERFACE_FAMILIES = ("Ubuntu", "Segoe UI", "Noto Sans", "Sans Serif")


def load_bundled_fonts() -> str | None:
    """Register the bundled Urdu font and return its family name.

    The font file is already on disk. Nothing is downloaded at runtime.
    The full variable font is tried first, then the static fallback.
    """
    folder = fonts_dir()
    for name in ("NotoNaskhArabic-Variable.ttf", "NotoNaskhArabic-Regular.ttf"):
        path = folder / name
        if not path.is_file():
            continue
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id < 0:
            continue
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families:
            set_preferred_urdu_family(families[0])
            return families[0]
    return None


def set_preferred_urdu_family(family: str | None) -> None:
    """Remember the bundled family so editors can request it by name."""
    global _preferred_urdu_family
    _preferred_urdu_family = family


def urdu_font(point_size: int) -> QFont:
    """A font stack that can draw Urdu on Ubuntu and Windows."""
    families: list[str] = []
    if _preferred_urdu_family:
        families.append(_preferred_urdu_family)
    families.extend(_URDU_FALLBACKS)
    font = QFont()
    font.setFamilies(families)
    font.setPointSize(point_size)
    return font


def interface_font(point_size: int = 11) -> QFont:
    """The font used for controls and English text."""
    font = QFont()
    font.setFamilies(list(_INTERFACE_FAMILIES))
    font.setPointSize(point_size)
    return font


def build_app_icon() -> QIcon:
    """Paint a simple mark so the window has an icon without an extra asset."""
    size = 64
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#1d3c34"))
    painter.drawRoundedRect(0, 0, size, size, 14, 14)
    painter.setPen(QColor("#f6f1e7"))
    font = QFont()
    font.setFamilies(list(_INTERFACE_FAMILIES))
    font.setPixelSize(18)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "U→E")
    painter.end()
    return QIcon(pixmap)
