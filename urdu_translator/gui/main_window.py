"""The Urdu and English window."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent, QGuiApplication, QKeySequence, QTextCursor
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from urdu_translator.documents import read_document, write_docx, write_txt
from urdu_translator.errors import AppError
from urdu_translator.gui.appearance import (
    Appearance,
    contrast_problems,
    load_appearance,
    save_appearance,
    stylesheet,
)
from urdu_translator.gui.appearance_dialog import AppearanceDialog
from urdu_translator.gui.editors import Editor, SourceEditor, configure_editor
from urdu_translator.gui.fonts import interface_font, urdu_font
from urdu_translator.gui.history_dialog import HistoryDialog
from urdu_translator.history.store import HistoryRecord, HistoryStore, readable_english
from urdu_translator.paths import database_path, models_dir
from urdu_translator.translation.backends.llama_server import stop_owned_server
from urdu_translator.translation.loader import EngineStatus, inspect_engine
from urdu_translator.translation.service import TranslationResult
from urdu_translator.workers.translate_worker import TranslateWorker

logger = logging.getLogger("urdu_translator.window")


class MainWindow(QMainWindow):
    """Side-by-side editor for Urdu source text and its English translation."""

    def __init__(
        self,
        models_directory: Path | None = None,
        history_database: Path | None = None,
        settings_path: Path | None = None,
    ) -> None:
        super().__init__()
        self.models_directory = Path(models_directory) if models_directory else models_dir()
        self.history_database = Path(history_database) if history_database else database_path()
        self.settings_path = Path(settings_path) if settings_path else None
        self.history: HistoryStore | None = None
        self._thread: TranslateWorker | None = None
        self._busy = False
        self._centered = False

        self.setWindowTitle("Urdu → English")
        self.setMinimumSize(1100, 720)
        self.resize(1280, 840)
        self.appearance = load_appearance(self.settings_path)

        self._build_ui()
        self.apply_appearance(self.appearance, persist=False)
        self._prepare_storage()
        self.refresh_model_status()
        self._update_counts()
        self._update_action_states()
        self.statusBar().showMessage("Ready")

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(22, 18, 22, 12)
        layout.setSpacing(14)

        layout.addLayout(self._build_header())

        self.urdu_editor = SourceEditor()
        configure_editor(
            self.urdu_editor,
            font=urdu_font(18),
            direction=Qt.LayoutDirection.RightToLeft,
            text_direction=Qt.LayoutDirection.LeftToRight,
            alignment=Qt.AlignmentFlag.AlignRight,
            placeholder="اردو متن یہاں لکھیں یا چسپاں کریں",
        )
        self.urdu_editor.document_dropped.connect(self._open_path)
        self.urdu_editor.textChanged.connect(self._on_urdu_changed)

        self.english_editor = Editor()
        configure_editor(
            self.english_editor,
            font=interface_font(14),
            direction=Qt.LayoutDirection.LeftToRight,
            alignment=Qt.AlignmentFlag.AlignLeft,
            placeholder="The English translation will appear here. You can edit it before saving.",
        )
        self.english_editor.textChanged.connect(self._on_english_changed)

        self.open_button = QPushButton("Open")
        self.open_button.setToolTip("Open a .txt or .docx file into the Urdu panel")
        self.open_button.setShortcut(QKeySequence.StandardKey.Open)
        self.open_button.clicked.connect(self.open_document)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(14)
        splitter.addWidget(self._build_panel(
            "Urdu",
            "Right to left",
            self.urdu_editor,
            object_name="Panel",
            corner=self.open_button,
            colour_panel="urdu",
        ))
        splitter.addWidget(self._build_panel(
            "English",
            "Left to right · editable",
            self.english_editor,
            object_name="EnglishPanel",
            colour_panel="literal",
        ))
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, stretch=1)

        self.banner = QFrame()
        self.banner.setObjectName("ErrorBanner")
        banner_layout = QHBoxLayout(self.banner)
        banner_layout.setContentsMargins(14, 10, 10, 10)
        self.banner_label = QLabel()
        self.banner_label.setObjectName("BannerText")
        self.banner_label.setWordWrap(True)
        self.banner_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        dismiss = QPushButton("Dismiss")
        dismiss.setObjectName("QuietButton")
        dismiss.clicked.connect(self._hide_banner)
        banner_layout.addWidget(self.banner_label, stretch=1)
        banner_layout.addWidget(dismiss, alignment=Qt.AlignmentFlag.AlignTop)
        self.banner.hide()
        layout.addWidget(self.banner)

        layout.addLayout(self._build_actions())
        self.setStatusBar(QStatusBar())
        self._build_status_widgets()

    def _build_header(self) -> QHBoxLayout:
        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(2)
        title = QLabel("Urdu → English")
        title.setObjectName("Title")
        subtitle = QLabel("Offline desktop translator")
        subtitle.setObjectName("Subtitle")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header.addLayout(titles)
        header.addStretch(1)

        self.history_button = QPushButton("History")
        self.history_button.setToolTip("Open translations saved on this computer")
        self.history_button.clicked.connect(self.show_history)
        header.addWidget(self.history_button)

        self.model_pill = QPushButton("Checking model…")
        self.model_pill.setObjectName("ModelPill")
        self.model_pill.setCursor(Qt.CursorShape.PointingHandCursor)
        self.model_pill.clicked.connect(self.show_model_details)
        header.addWidget(self.model_pill)
        return header

    def _build_panel(
        self,
        title: str,
        caption: str,
        editor: QPlainTextEdit,
        *,
        object_name: str,
        corner: QPushButton | None = None,
        colour_panel: str | None = None,
    ) -> QFrame:
        panel = QFrame()
        panel.setObjectName(object_name)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(6)

        heading = QHBoxLayout()
        label = QLabel(title)
        label.setObjectName("PanelTitle")
        heading.addWidget(label)
        heading.addStretch(1)
        if colour_panel is not None:
            colour_button = QPushButton("Colour")
            colour_button.setToolTip(f"Choose text and background colours for {title}")
            colour_button.clicked.connect(lambda _checked=False, panel=colour_panel: self.choose_colours(panel))
            if colour_panel == "urdu":
                self.urdu_colour_button = colour_button
            else:
                self.literal_colour_button = colour_button
            heading.addWidget(colour_button)
        if corner is not None:
            heading.addWidget(corner)
        layout.addLayout(heading)

        caption_label = QLabel(caption)
        caption_label.setObjectName("PanelCaption")
        layout.addWidget(caption_label)
        layout.addWidget(editor, stretch=1)
        return panel

    def _build_actions(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        self.translate_button = QPushButton("Translate")
        self.translate_button.setObjectName("PrimaryButton")
        self.translate_button.setShortcut(QKeySequence("Ctrl+Return"))
        self.translate_button.setToolTip("Translate the Urdu panel (Ctrl+Enter)")
        self.translate_button.clicked.connect(self.translate)

        self.clear_button = QPushButton("Clear")
        self.clear_button.setToolTip("Clear all panels")
        self.clear_button.clicked.connect(self.clear_editors)

        self.copy_button = QPushButton("Copy")
        self.copy_button.setShortcut(QKeySequence("Ctrl+Shift+C"))
        self.copy_button.setToolTip("Copy the English translation (Ctrl+Shift+C)")
        self.copy_button.clicked.connect(self.copy_translation)

        self.save_button = QPushButton("Save TXT")
        self.save_button.setShortcut(QKeySequence.StandardKey.Save)
        self.save_button.setToolTip("Save the English translation as a text file (Ctrl+S)")
        self.save_button.clicked.connect(self.save_txt)

        self.export_button = QPushButton("Export DOCX")
        self.export_button.setShortcut(QKeySequence("Ctrl+Shift+E"))
        self.export_button.setToolTip("Export the English translation to Word (Ctrl+Shift+E)")
        self.export_button.clicked.connect(self.export_docx)

        row.addWidget(self.translate_button)
        row.addWidget(self.clear_button)
        row.addStretch(1)
        row.addWidget(self.copy_button)
        row.addWidget(self.save_button)
        row.addWidget(self.export_button)
        return row

    def _build_status_widgets(self) -> None:
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setFixedWidth(140)
        self.progress.hide()
        self.source_count = QLabel("Urdu  0")
        self.source_count.setObjectName("CountLabel")
        self.target_count = QLabel("English  0")
        self.target_count.setObjectName("CountLabel")
        status = self.statusBar()
        status.addPermanentWidget(self.progress)
        status.addPermanentWidget(self.source_count)
        status.addPermanentWidget(self.target_count)

    def _prepare_storage(self) -> None:
        try:
            self.models_directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.error("Could not create the models folder: %s", exc)
        try:
            self.history = HistoryStore(self.history_database)
        except sqlite3.Error as exc:
            self.history = None
            logger.error("Could not open translation history: %s", exc)
            QTimer.singleShot(
                0,
                lambda: self._show_banner(
                    f"Translation history is unavailable. {exc}",
                    kind="warning",
                ),
            )

    def refresh_model_status(self) -> EngineStatus:
        """Re-read the models folder and update the status pill."""
        try:
            status = inspect_engine(self.models_directory)
        except OSError as exc:
            status = EngineStatus("invalid", "Check model setup", f"Could not read the models folder. {exc}")
        self._apply_engine_status(status)
        return status

    def _apply_engine_status(self, status: EngineStatus) -> None:
        self.model_pill.setText(status.short_label)
        self.model_pill.setToolTip(status.message)
        self.model_pill.setProperty("state", status.state)
        self._repolish(self.model_pill)

    def apply_appearance(self, appearance: Appearance, *, persist: bool) -> None:
        """Paint the window from the shared theme. Direction settings are left alone."""
        self.appearance = appearance
        self.setStyleSheet(stylesheet(appearance))
        if persist:
            save_appearance(appearance, self.settings_path)

    def choose_colours(self, _panel: str = "urdu") -> None:
        """Open the colour dialog. Readable drafts are shown on the window immediately."""
        if self._busy:
            return
        previous = self.appearance
        dialog = AppearanceDialog(
            previous,
            self,
            on_change=lambda draft: self.apply_appearance(draft, persist=False),
        )
        if dialog.exec() and not contrast_problems(dialog.appearance()):
            self.apply_appearance(dialog.appearance(), persist=True)
            self.statusBar().showMessage("Saved text colours.")
            return
        self.apply_appearance(previous, persist=False)

    def show_model_details(self) -> None:
        """Show the current model-folder message in the banner."""
        status = self.refresh_model_status()
        kind = "info" if status.state == "ready" else "warning"
        self._show_banner(status.message, kind=kind)

    def translate(self) -> None:
        """Start a background translation of the current Urdu text."""
        if self._busy:
            return
        text = self.urdu_editor.toPlainText()
        if not text.strip():
            self._show_banner("Enter or open Urdu text before translating.", kind="warning")
            return
        self._hide_banner()
        self._set_busy(True)
        self.statusBar().showMessage("Starting translation…")
        worker = TranslateWorker(text, self.models_directory)
        worker.succeeded.connect(self._on_translated)
        worker.failed.connect(self._on_translation_failed)
        worker.cancelled.connect(self._on_translation_cancelled)
        worker.status_message.connect(self.statusBar().showMessage)
        worker.finished.connect(self._on_worker_finished)
        self._thread = worker
        worker.start()

    def clear_editors(self) -> None:
        """Clear both panels after a confirmation when either one has text."""
        if self._busy:
            return
        if self.urdu_editor.toPlainText() or self.english_editor.toPlainText():
            if not self._confirm("Clear both text panels?"):
                return
        self._clear_documents()

    def _clear_documents(self) -> None:
        self.urdu_editor.clear()
        self.english_editor.clear()
        self._hide_banner()
        self.statusBar().showMessage("Cleared both panels.")

    def copy_translation(self) -> None:
        """Copy the English panel to the clipboard."""
        self._copy_editor(self.english_editor, "Copied the English translation.", "There is no English translation to copy.")

    def save_txt(self) -> None:
        """Save the English panel as a UTF-8 text file."""
        self._export_editor(
            self.english_editor,
            title="Save translation",
            default_name="translation.txt",
            file_filter="Text files (*.txt)",
            suffix=".txt",
            writer=write_txt,
            empty_message="There is no English translation to save.",
        )

    def export_docx(self) -> None:
        """Export the English panel to a Word document."""
        self._export_editor(
            self.english_editor,
            title="Export translation",
            default_name="translation.docx",
            file_filter="Word documents (*.docx)",
            suffix=".docx",
            writer=write_docx,
            empty_message="There is no English translation to save.",
        )

    def open_document(self) -> None:
        """Load a text or Word file into the Urdu panel."""
        if self._busy:
            return
        path, _selected = QFileDialog.getOpenFileName(
            self,
            "Open Urdu text",
            str(Path.home()),
            "Documents (*.txt *.docx);;Text files (*.txt);;Word documents (*.docx)",
        )
        if path:
            self._open_path(path)

    def show_history(self) -> None:
        """Open the saved-translation dialog."""
        if self._busy:
            return
        if self.history is None:
            self._show_banner("Translation history is unavailable.", kind="warning")
            return
        dialog = HistoryDialog(self.history, self, appearance=self.appearance)
        if dialog.exec() and dialog.selected_record is not None:
            self._load_history_record(dialog.selected_record)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt API
        thread = self._thread
        if thread is not None and thread.isRunning():
            thread.requestInterruption()
            thread.wait(10000)
        if thread is None or not thread.isRunning():
            stop_owned_server()
        super().closeEvent(event)

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        if not self._centered:
            self._centered = True
            self._center_on_screen()

    def _open_path(self, path: str) -> None:
        if self._busy:
            return
        if self.urdu_editor.toPlainText().strip() and not self._confirm(
            "Replace the Urdu text with this file?"
        ):
            return
        try:
            text = read_document(Path(path))
        except AppError as exc:
            self._show_banner(str(exc), kind="error")
            return
        self.urdu_editor.setPlainText(text)
        self._hide_banner()
        self.statusBar().showMessage(f"Opened {Path(path).name}.")

    def _load_history_record(self, record: HistoryRecord) -> None:
        has_text = bool(self.urdu_editor.toPlainText() or self.english_editor.toPlainText())
        if has_text and not self._confirm("Replace the panels with this saved translation?"):
            return
        self.urdu_editor.setPlainText(record.source_text)
        self.english_editor.setPlainText(readable_english(record))
        self._hide_banner()
        self.statusBar().showMessage("Opened a saved translation.")

    def _copy_editor(self, editor: QPlainTextEdit, success: str, empty_message: str) -> None:
        text = editor.toPlainText()
        if not text.strip():
            self._show_banner(empty_message, kind="warning")
            return
        QGuiApplication.clipboard().setText(text)
        self._hide_banner()
        self.statusBar().showMessage(success)

    def _export_editor(
        self,
        editor: QPlainTextEdit,
        *,
        title: str,
        default_name: str,
        file_filter: str,
        suffix: str,
        writer,
        empty_message: str,
    ) -> None:
        text = editor.toPlainText()
        if not text.strip():
            self._show_banner(empty_message, kind="warning")
            return
        path, _selected = QFileDialog.getSaveFileName(
            self,
            title,
            str(Path.home() / default_name),
            file_filter,
        )
        if not path:
            return
        destination = Path(path)
        if destination.suffix.lower() != suffix:
            destination = destination.with_suffix(suffix)
        self._write_export(destination, text, writer)

    def _write_export(self, destination: Path, text: str, writer) -> None:
        try:
            writer(destination, text)
        except AppError as exc:
            self._show_banner(str(exc), kind="error")
            return
        self._hide_banner()
        self.statusBar().showMessage(f"Saved {destination.name}.")

    def _on_translated(self, result: TranslationResult) -> None:
        self._set_editor_text(self.english_editor, result.text)
        self._hide_banner()
        if result.translated_segment_count:
            self._remember(result)
            self.statusBar().showMessage(
                f"Translated {result.translated_segment_count} lines with {result.engine_name}."
            )
        else:
            self.statusBar().showMessage("No Urdu text needed translation. The original lines were kept.")
        self.refresh_model_status()

    def _remember(self, result: TranslationResult) -> None:
        if self.history is None:
            self._show_banner(
                "The translation is on screen, but history is unavailable.",
                kind="warning",
            )
            return
        try:
            self.history.add(
                source_text=result.source_text,
                translated_text=result.text,
                engine_name=result.engine_name or "Unknown model",
            )
        except sqlite3.Error as exc:
            logger.error("Could not save history: %s", exc)
            self._show_banner(
                f"The translation is on screen, but it could not be saved to history. {exc}",
                kind="warning",
            )

    def _on_translation_failed(self, message: str) -> None:
        self._show_banner(message, kind="error")
        self.statusBar().showMessage("Translation needs attention.")
        self.refresh_model_status()

    def _on_translation_cancelled(self) -> None:
        self.statusBar().showMessage("Translation cancelled.")

    def _on_worker_finished(self) -> None:
        thread = self._thread
        self._thread = None
        self._set_busy(False)
        if thread is not None:
            thread.deleteLater()

    def _on_urdu_changed(self) -> None:
        self._update_counts()
        self._update_action_states()

    def _on_english_changed(self) -> None:
        self._update_counts()
        self._update_action_states()

    def _update_counts(self) -> None:
        urdu_chars = len(self.urdu_editor.toPlainText())
        english_chars = len(self.english_editor.toPlainText())
        self.source_count.setText(f"Urdu  {urdu_chars:,}")
        self.target_count.setText(f"English  {english_chars:,}")

    def _update_action_states(self) -> None:
        if self._busy:
            return
        has_source = bool(self.urdu_editor.toPlainText().strip())
        has_translation = bool(self.english_editor.toPlainText().strip())
        has_any = bool(self.urdu_editor.toPlainText() or self.english_editor.toPlainText())
        self.translate_button.setEnabled(has_source)
        self.clear_button.setEnabled(has_any)
        self.copy_button.setEnabled(has_translation)
        self.save_button.setEnabled(has_translation)
        self.export_button.setEnabled(has_translation)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.translate_button.setText("Translating…" if busy else "Translate")
        self.translate_button.setEnabled(not busy)
        self.open_button.setEnabled(not busy)
        self.clear_button.setEnabled(not busy)
        self.history_button.setEnabled(not busy)
        if busy:
            self.progress.show()
        else:
            self.progress.hide()
            self._update_action_states()

    @staticmethod
    def _set_editor_text(editor: QPlainTextEdit, text: str) -> None:
        editor.setPlainText(text)
        cursor = editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        editor.setTextCursor(cursor)

    def _show_banner(self, message: str, *, kind: str) -> None:
        self.banner.setProperty("kind", kind)
        self._repolish(self.banner)
        self.banner_label.setText(message)
        self.banner.show()

    def _hide_banner(self) -> None:
        self.banner.hide()
        self.banner_label.clear()

    def _confirm(self, message: str) -> bool:
        answer = QMessageBox.question(
            self,
            "Urdu → English",
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _center_on_screen(self) -> None:
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            return
        frame = self.frameGeometry()
        frame.moveCenter(screen.availableGeometry().center())
        self.move(frame.topLeft())

    @staticmethod
    def _repolish(widget: QWidget) -> None:
        style = widget.style()
        style.unpolish(widget)
        style.polish(widget)
