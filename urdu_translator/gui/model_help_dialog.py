"""First-launch and Help guidance for installing the Gemma GGUF from USB."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from urdu_translator.gui.appearance import stylesheet
from urdu_translator.model_setup import EXPECTED_GGUF, READY_STATUS, load_saved_model_path
from urdu_translator.paths import recommended_models_dir


class ModelHelpDialog(QDialog):
    """Explain offline Gemma setup without downloading or moving the model."""

    def __init__(self, parent=None, *, model_ready: bool = False) -> None:
        super().__init__(parent)
        self.setWindowTitle("Gemma Model Installation")
        self.setModal(True)
        self.setMinimumWidth(560)
        self.setStyleSheet(stylesheet())
        self._wants_setup = False
        self._model_ready = model_ready

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(12)

        title = QLabel("Gemma Model Installation")
        title.setObjectName("Title")
        layout.addWidget(title)

        intro = QLabel(
            "Urdu Translator runs completely offline. The Gemma translation model "
            "is not included in the Windows installer. Copy it to this computer "
            "from a USB drive or other local storage."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        filename = QLabel(f"Required model filename: {EXPECTED_GGUF}")
        filename.setWordWrap(True)
        layout.addWidget(filename)

        models = recommended_models_dir()
        folder = QLabel(
            "Recommended model folder:\n"
            f"{models}\n\n"
            "If that folder does not exist yet, Open Model Folder creates it. "
            "You can also keep the file on a USB drive and point the setup "
            "screen at that location."
        )
        folder.setWordWrap(True)
        folder.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(folder)

        example = QLabel(
            "Example path:\n"
            f"{Path(models) / EXPECTED_GGUF}"
        )
        example.setWordWrap(True)
        example.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(example)

        status = QLabel(self._status_text())
        status.setObjectName("SummaryStatus")
        status.setWordWrap(True)
        layout.addWidget(status)

        note = QLabel(
            "The application does not download, rename, move, or delete the model. "
            "Use Browse for Model on the setup screen when you are ready to verify it."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        self.skip_box = QCheckBox("Don't show this again")
        layout.addWidget(self.skip_box)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)

        open_folder = QPushButton("Open Model Folder")
        open_folder.clicked.connect(self.open_model_folder)

        self.start_button = QPushButton("Get Started" if not model_ready else "Close")
        self.start_button.setObjectName("PrimaryButton")
        self.start_button.clicked.connect(self._accept_start)

        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        if model_ready:
            close.hide()

        buttons.addWidget(open_folder)
        buttons.addStretch(1)
        buttons.addWidget(close)
        buttons.addWidget(self.start_button)
        layout.addLayout(buttons)

    def dont_show_again(self) -> bool:
        return self.skip_box.isChecked()

    def wants_setup(self) -> bool:
        return self._wants_setup and not self._model_ready

    def open_model_folder(self) -> None:
        """Create the recommended folder when needed and open it in the file manager."""
        folder = recommended_models_dir()
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _accept_start(self) -> None:
        self._wants_setup = not self._model_ready
        self.accept()

    def _status_text(self) -> str:
        if self._model_ready:
            return f"Model status: {READY_STATUS}"
        saved = load_saved_model_path()
        if saved is not None and saved.is_file():
            return f"Model status: file recorded at {saved}. Verify it from the setup screen if translation is unavailable."
        return (
            "Model status: not configured yet. "
            "After you copy the GGUF file, use Get Started to browse and verify it."
        )
