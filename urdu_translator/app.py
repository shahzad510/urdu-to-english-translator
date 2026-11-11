"""Application startup."""

from __future__ import annotations

import logging
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from urdu_translator import __version__
from urdu_translator.gui.fonts import build_app_icon, interface_font, load_bundled_fonts
from urdu_translator.gui.main_window import MainWindow
from urdu_translator.paths import log_path

logger = logging.getLogger("urdu_translator")


def configure_logging() -> None:
    """Write diagnostic lines to the user data folder.

    Source documents are not logged. Backend exceptions should stay short
    and should not include the text being translated.
    """
    if any(isinstance(handler, logging.FileHandler) for handler in logger.handlers):
        return
    logger.setLevel(logging.INFO)
    try:
        handler = logging.FileHandler(log_path(), encoding="utf-8")
    except OSError:
        return
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger.addHandler(handler)


def main() -> int:
    """Create the Qt application and show the translator window."""
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    application = QApplication(sys.argv)
    application.setApplicationName("Urdu to English")
    application.setApplicationVersion(__version__)
    application.setOrganizationName("UrduTranslator")
    application.setStyle("Fusion")
    configure_logging()
    load_bundled_fonts()
    application.setFont(interface_font(11))
    application.setWindowIcon(build_app_icon())
    window = MainWindow()
    window.show()
    window.offer_first_launch_guidance()
    window.offer_model_setup()
    return application.exec()
