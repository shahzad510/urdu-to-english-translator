"""First-run dialog for the Gemma GGUF file that arrives on a USB drive."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)

from urdu_translator.errors import TranslationFailedError
from urdu_translator.gui.appearance import stylesheet
from urdu_translator.model_setup import (
    EXPECTED_GGUF,
    READY_STATUS,
    confirm_server_can_open,
    copy_model_file,
    load_saved_model_path,
    register_gemma_engine,
    save_model_path,
    validate_model_file,
)
from urdu_translator.paths import bundled_llama_server, recommended_models_dir


class ModelSetupDialog(QDialog):
    """Let the user point at a GGUF file and check that llama-server can open it."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Gemma AI Model Setup")
        self.setModal(True)
        self.setMinimumWidth(640)
        self.setStyleSheet(stylesheet())
        self.selected_path: Path | None = load_saved_model_path()
        self._verified = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(12)

        title = QLabel("Gemma AI Model Setup")
        title.setObjectName("Title")
        layout.addWidget(title)

        explanation = QLabel(
            "Urdu Translator operates completely offline. To enable translation and "
            "summarisation, copy the Gemma 4 E4B model file to this computer using USB."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)

        filename = QLabel(f"Required model filename: {EXPECTED_GGUF}")
        filename.setWordWrap(True)
        layout.addWidget(filename)

        availability = QLabel(
            "The model is transferred separately. It is not included in the installer "
            "and the application will not download it. A USB drive, local disk, or "
            "other external storage can be used."
        )
        availability.setWordWrap(True)
        layout.addWidget(availability)

        self.path_label = QLabel(self._path_text())
        self.path_label.setWordWrap(True)
        self.path_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self.path_label)

        self.keep_button = QRadioButton("Keep model at its current location")
        self.copy_button = QRadioButton(
            f"Copy model to the recommended local model directory\n"
            f"{recommended_models_dir()}"
        )
        self.keep_button.setChecked(True)

        group = QButtonGroup(self)
        group.addButton(self.keep_button)
        group.addButton(self.copy_button)

        layout.addWidget(self.keep_button)
        layout.addWidget(self.copy_button)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.hide()
        layout.addWidget(self.progress)

        self.status_label = QLabel("Model Status: not selected")
        self.status_label.setWordWrap(True)
        self.status_label.setObjectName("SummaryStatus")
        layout.addWidget(self.status_label)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)

        self.browse_button = QPushButton("Browse for Model")
        self.browse_button.clicked.connect(self.browse)

        self.verify_button = QPushButton("Verify Model")
        self.verify_button.setObjectName("PrimaryButton")
        self.verify_button.clicked.connect(self.verify)

        close = QPushButton("Close")
        close.clicked.connect(self.reject)

        buttons.addWidget(self.browse_button)
        buttons.addWidget(self.verify_button)
        buttons.addStretch(1)
        buttons.addWidget(close)

        layout.addLayout(buttons)

        if self.selected_path is not None:
            self._show_file_status(self.selected_path)

    def _path_text(self) -> str:
        if self.selected_path is None:
            return "Selected file: none"
        return f"Selected file: {self.selected_path}"

    def browse(self) -> None:
        """Ask for a GGUF file on a USB drive, local disk, or other storage."""
        start = (
            str(self.selected_path.parent)
            if self.selected_path is not None
            else ""
        )

        chosen, _filter = QFileDialog.getOpenFileName(
            self,
            "Select the Gemma model",
            start,
            "GGUF model (*.gguf);;All files (*)",
        )

        if not chosen:
            return

        self.selected_path = Path(chosen)
        self._verified = False
        self.path_label.setText(self._path_text())
        self._show_file_status(self.selected_path)

    def verify(self) -> None:
        """Check the file, optionally copy it, and register the verified engine."""
        if self.selected_path is None:
            self.status_label.setText(
                "Model Status: choose the Gemma model file first."
            )
            return

        problem = validate_model_file(self.selected_path)

        if problem:
            self._verified = False
            self.status_label.setText(f"Model Status: {problem}")
            return

        destination = self.selected_path

        if self.copy_button.isChecked():
            self.progress.show()
            self.progress.setValue(0)

            def report(copied: int, total: int) -> None:
                if total <= 0:
                    return

                self.progress.setValue(
                    min(100, int(copied * 100 / total))
                )
                QApplication.processEvents()

            try:
                destination = copy_model_file(
                    self.selected_path,
                    progress=report,
                )
            except TranslationFailedError as exc:
                self._verified = False
                self.status_label.setText(f"Model Status: {exc}")
                return

            self.progress.setValue(100)

        binary = self._server_binary()

        if binary is None:
            self._verified = False
            self.status_label.setText(
                "Model Status: llama-server.exe was not found beside the "
                "application. The model file was not deleted."
            )
            return

        issue = confirm_server_can_open(destination, binary)

        if issue:
            self._verified = False
            self.status_label.setText(f"Model Status: {issue}")
            return

        # The server successfully loaded the model.
        # Now register Gemma so the main application can discover it.
        try:
            register_gemma_engine()
            save_model_path(destination)
        except (TranslationFailedError, OSError) as exc:
            self._verified = False
            self.status_label.setText(
                f"Model Status: the model loaded successfully, but its "
                f"configuration could not be saved. {exc}"
            )
            return

        self.selected_path = destination
        self.path_label.setText(self._path_text())
        self._verified = True

        self.status_label.setText(f"Model Status: {READY_STATUS}")

        self.accept()

    def _show_file_status(self, path: Path) -> None:
        problem = validate_model_file(path)

        if problem:
            self.status_label.setText(f"Model Status: {problem}")
            return

        self.status_label.setText(
            "Model Status: file found. Choose Verify Model to load it offline."
        )

    def _server_binary(self) -> Path | None:
        bundled = bundled_llama_server()

        if bundled is not None:
            return bundled

        parent = self.parent()
        models = getattr(parent, "models_directory", None)

        if models is None:
            return None

        from urdu_translator.translation.backends.gemma import (
            resolve_server_binary,
        )
        from urdu_translator.translation.loader import (
            discover_packages,
            select_package,
        )

        try:
            packages = discover_packages(Path(models))
            package = (
                select_package(packages, Path(models))
                if packages
                else None
            )
        except Exception:
            return None

        if package is None or package.backend != "gemma":
            return None

        try:
            return resolve_server_binary(package)
        except Exception:
            return None