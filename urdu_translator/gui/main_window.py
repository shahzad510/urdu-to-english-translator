"""The Urdu and English window."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent, QGuiApplication, QKeySequence, QTextCursor
from PySide6.QtWidgets import (
    QComboBox,
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

from urdu_translator.documents import read_document, write_translation_docx, write_txt
from urdu_translator.errors import AppError
from urdu_translator.gui.appearance import apply_editor_colors, stylesheet
from urdu_translator.gui.editors import Editor, SourceEditor, configure_editor
from urdu_translator.gui.fonts import interface_font, urdu_font
from urdu_translator.gui.history_dialog import HistoryDialog
from urdu_translator.history.store import HistoryRecord, HistoryStore, readable_english
from urdu_translator.paths import database_path, models_dir
from urdu_translator.translation.backends.llama_server import stop_owned_server
from urdu_translator.translation.loader import EngineStatus, inspect_engine
from urdu_translator.translation.gist import level_label, next_summary_level
from urdu_translator.translation.service import TranslationResult
from urdu_translator.workers.gist_worker import GistWorker
from urdu_translator.workers.translate_worker import TranslateWorker

logger = logging.getLogger("urdu_translator.window")

_GIST_PLACEHOLDER = "Contextual summary will appear here after translation."
_GIST_WORKING = "Writing the contextual summary…"


class MainWindow(QMainWindow):
    """Side-by-side editor for Urdu source text and its English translation."""

    def __init__(
        self,
        models_directory: Path | None = None,
        history_database: Path | None = None,
    ) -> None:
        super().__init__()
        self.models_directory = Path(models_directory) if models_directory else models_dir()
        self.history_database = Path(history_database) if history_database else database_path()
        self.history: HistoryStore | None = None
        self._thread: TranslateWorker | GistWorker | None = None
        self._busy = False
        self._centered = False
        self._gist_state = "empty"
        self._gist_running = False
        self._gist_level = ""
        self._gist_source = ""
        self._gist_request_level = "brief"
        self._gist_request_source = ""
        self._gist_backup: tuple[str, str, str, str] | None = None
        self._pending_retry_level = ""

        self.setWindowTitle("Urdu → English")
        self.setMinimumSize(1100, 720)
        self.resize(1280, 840)
        self._build_ui()
        self._apply_theme()
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

        self.gist_editor = Editor()
        configure_editor(
            self.gist_editor,
            font=interface_font(14),
            direction=Qt.LayoutDirection.LeftToRight,
            alignment=Qt.AlignmentFlag.AlignLeft,
            placeholder=_GIST_PLACEHOLDER,
        )
        self.gist_editor.setReadOnly(True)
        self.gist_editor.setMinimumHeight(120)
        self.gist_editor.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )

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
        ))
        self.detail_splitter = QSplitter(Qt.Orientation.Vertical)
        self.detail_splitter.setChildrenCollapsible(False)
        self.detail_splitter.setHandleWidth(14)
        self.detail_splitter.addWidget(self._build_panel(
            "English",
            "Left to right · editable",
            self.english_editor,
            object_name="EnglishPanel",
        ))
        self.detail_splitter.addWidget(self._build_gist_panel())
        self.detail_splitter.setStretchFactor(0, 3)
        self.detail_splitter.setStretchFactor(1, 2)
        self.detail_splitter.setSizes([420, 200])
        splitter.addWidget(self.detail_splitter)
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
        if corner is not None:
            heading.addWidget(corner)
        layout.addLayout(heading)

        caption_label = QLabel(caption)
        caption_label.setObjectName("PanelCaption")
        layout.addWidget(caption_label)
        layout.addWidget(editor, stretch=1)
        return panel

    def _build_gist_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("GistPanel")
        panel.setMinimumHeight(180)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(6)

        heading = QHBoxLayout()
        label = QLabel("Gist / Contextual Summary")
        label.setObjectName("PanelTitle")
        heading.addWidget(label)
        heading.addStretch(1)
        self.gist_level_label = QLabel("")
        self.gist_level_label.setObjectName("PanelTitle")
        heading.addWidget(self.gist_level_label)
        layout.addLayout(heading)

        self.gist_caption = QLabel("Read only")
        self.gist_caption.setObjectName("PanelCaption")
        layout.addWidget(self.gist_caption)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.copy_gist_button = QPushButton("Copy Gist")
        self.copy_gist_button.setToolTip("Copy the contextual summary")
        self.copy_gist_button.clicked.connect(self.copy_gist)
        self.save_gist_button = QPushButton("Save Gist as TXT")
        self.save_gist_button.setToolTip("Save the contextual summary as a text file")
        self.save_gist_button.clicked.connect(self.save_gist)
        self.summarize_further_button = QPushButton("Summarize Further")
        self.summarize_further_button.setToolTip(
            "Write a longer summary from the full English translation."
        )
        self.summarize_further_button.clicked.connect(self.summarize_further)
        self.gist_level_choice = QComboBox()
        self.gist_level_choice.addItems(["Brief", "Detailed", "Expanded"])
        self.gist_level_choice.setToolTip("Summary length")
        self.gist_level_choice.hide()
        self.use_level_button = QPushButton("Regenerate")
        self.use_level_button.setToolTip(
            "Regenerate the selected summary level from the full English translation."
        )
        self.use_level_button.clicked.connect(self.regenerate_selected_level)
        self.use_level_button.hide()
        self.gist_retry_button = QPushButton("Retry")
        self.gist_retry_button.setToolTip("Write the contextual summary again")
        self.gist_retry_button.clicked.connect(self.retry_gist)
        self.gist_retry_button.hide()
        buttons.addWidget(self.copy_gist_button)
        buttons.addWidget(self.save_gist_button)
        buttons.addWidget(self.summarize_further_button)
        buttons.addWidget(self.gist_level_choice)
        buttons.addWidget(self.use_level_button)
        buttons.addWidget(self.gist_retry_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        layout.addWidget(self.gist_editor, stretch=1)
        self.gist_progress = QProgressBar()
        self.gist_progress.setRange(0, 0)
        self.gist_progress.setTextVisible(False)
        self.gist_progress.setFixedHeight(6)
        self.gist_progress.hide()
        layout.addWidget(self.gist_progress)
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
        self.export_button.setToolTip(
            "Export the Urdu text, English translation, and contextual summary to Word (Ctrl+Shift+E)"
        )
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

    def _apply_theme(self) -> None:
        """Paint the window and both editors. Direction settings are left alone."""
        self.setStyleSheet(stylesheet())
        apply_editor_colors(self.urdu_editor)
        apply_editor_colors(self.english_editor)
        apply_editor_colors(self.gist_editor)

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
        self._reset_gist()
        self._gist_request_level = "brief"
        self._set_busy(True)
        self.statusBar().showMessage("Starting translation…")
        worker = TranslateWorker(text, self.models_directory)
        self._start_worker(worker)

    def clear_editors(self) -> None:
        """Clear the panels after a confirmation when any of them has text."""
        if self._busy:
            return
        if (
            self.urdu_editor.toPlainText()
            or self.english_editor.toPlainText()
            or self.gist_editor.toPlainText()
        ):
            if not self._confirm("Clear all text panels?"):
                return
        self._clear_documents()

    def _clear_documents(self) -> None:
        self.urdu_editor.clear()
        self.english_editor.clear()
        self._reset_gist()
        self._hide_banner()
        self.statusBar().showMessage("Cleared all panels.")

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

    def copy_gist(self) -> None:
        """Copy the contextual summary."""
        if self._gist_state not in {"ready", "outdated"}:
            self._show_banner("There is no contextual summary to copy.", kind="warning")
            return
        self._copy_editor(
            self.gist_editor,
            "Copied the contextual summary.",
            "There is no contextual summary to copy.",
        )

    def save_gist(self) -> None:
        """Save the contextual summary as a UTF-8 text file."""
        if self._gist_state not in {"ready", "outdated"}:
            self._show_banner("There is no contextual summary to save.", kind="warning")
            return
        self._export_editor(
            self.gist_editor,
            title="Save contextual summary",
            default_name="gist.txt",
            file_filter="Text files (*.txt)",
            suffix=".txt",
            writer=write_txt,
            empty_message="There is no contextual summary to save.",
        )

    def retry_gist(self) -> None:
        """Write the contextual summary again from the current English panel."""
        if self._gist_state == "outdated":
            self._request_gist(self._gist_level or "brief")
            return
        level = self._pending_retry_level or self._gist_level or "brief"
        self._request_gist(level)

    def summarize_further(self) -> None:
        """Write the next longer summary from the full English translation.

        Expanded is the longest level. Another click offers Brief or a
        regenerate at Brief, Detailed, or Expanded instead of growing further.
        """
        if self._busy or self._gist_state not in {"ready", "outdated"}:
            return
        nxt = next_summary_level(self._gist_level or "brief")
        if nxt is None:
            self.gist_level_choice.setCurrentText("Brief")
            self.gist_level_choice.show()
            self.use_level_button.show()
            self.statusBar().showMessage(
                "Expanded is the longest summary. Choose a level to regenerate."
            )
            return
        self._request_gist(nxt)

    def regenerate_selected_level(self) -> None:
        """Regenerate Brief, Detailed, or Expanded from the current English text."""
        selected = self.gist_level_choice.currentText().strip().lower()
        self._request_gist(selected or "brief")

    def _request_gist(self, level: str) -> None:
        """Summarise the current English text at ``level`` without changing it."""
        if self._busy:
            return
        english = self.english_editor.toPlainText()
        if not english.strip():
            self._show_banner("There is no English translation to summarise.", kind="warning")
            return
        if self._gist_state in {"ready", "outdated"} and self.gist_editor.toPlainText().strip():
            self._gist_backup = (
                self._gist_level,
                self.gist_editor.toPlainText(),
                self._gist_source,
                self._gist_state,
            )
        else:
            self._gist_backup = None
        self._gist_request_level = level or "brief"
        self._gist_request_source = english
        self._hide_banner()
        self.gist_level_choice.hide()
        self.use_level_button.hide()
        self._set_busy(True, label="Summarising…")
        self.statusBar().showMessage("Writing the contextual summary…")
        worker = GistWorker(english, self.models_directory, self._gist_request_level)
        worker.gist_started.connect(self._on_gist_started)
        worker.ready.connect(self._on_gist_ready)
        worker.failed.connect(self._on_gist_failed)
        worker.cancelled.connect(self._on_gist_cancelled)
        worker.status_message.connect(self._on_status_message)
        worker.finished.connect(self._on_worker_finished)
        self._thread = worker
        worker.start()

    def export_docx(self) -> None:
        """Export the Urdu text, English translation, and contextual summary."""
        english = self.english_editor.toPlainText()
        if not english.strip():
            self._show_banner("There is no English translation to save.", kind="warning")
            return
        path, _selected = QFileDialog.getSaveFileName(
            self,
            "Export translation",
            str(Path.home() / "translation.docx"),
            "Word documents (*.docx)",
        )
        if not path:
            return
        destination = Path(path)
        if destination.suffix.lower() != ".docx":
            destination = destination.with_suffix(".docx")
        show_gist = self._gist_state in {"ready", "outdated"}
        gist = self.gist_editor.toPlainText() if show_gist else ""
        gist_level = level_label(self._gist_level) if show_gist and self._gist_level else ""
        try:
            write_translation_docx(
                destination,
                urdu=self.urdu_editor.toPlainText(),
                english=english,
                gist=gist,
                gist_level=gist_level,
            )
        except AppError as exc:
            self._show_banner(str(exc), kind="error")
            return
        self._hide_banner()
        self.statusBar().showMessage(f"Saved {destination.name}.")

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
        dialog = HistoryDialog(self.history, self)
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
        self._reset_gist()
        self._hide_banner()
        self.statusBar().showMessage(f"Opened {Path(path).name}.")

    def _load_history_record(self, record: HistoryRecord) -> None:
        has_text = bool(
            self.urdu_editor.toPlainText()
            or self.english_editor.toPlainText()
            or self.gist_editor.toPlainText()
        )
        if has_text and not self._confirm("Replace the panels with this saved translation?"):
            return
        self._reset_gist()
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

    def _start_worker(self, worker: TranslateWorker) -> None:
        worker.succeeded.connect(self._on_translated)
        worker.failed.connect(self._on_translation_failed)
        worker.cancelled.connect(self._on_translation_cancelled)
        worker.gist_started.connect(self._on_gist_started)
        worker.gist_ready.connect(self._on_gist_ready)
        worker.gist_failed.connect(self._on_gist_failed)
        worker.gist_cancelled.connect(self._on_gist_cancelled)
        worker.status_message.connect(self._on_status_message)
        worker.finished.connect(self._on_worker_finished)
        self._thread = worker
        worker.start()

    def _on_status_message(self, message: str) -> None:
        self.statusBar().showMessage(message)
        if self._gist_running and (
            message.startswith("Writing the contextual summary")
            or message.startswith("Summarising part")
            or message.startswith("Combining the section")
        ):
            self.gist_caption.setText(message)

    def _on_translated(self, result: TranslationResult) -> None:
        self._gist_request_level = "brief"
        self._gist_request_source = result.text
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

    def _on_gist_started(self) -> None:
        self._gist_state = "running"
        self._gist_running = True
        self.gist_editor.setPlaceholderText(_GIST_WORKING)
        if self._gist_backup is None:
            self.gist_editor.clear()
        self.gist_caption.setText("Generating summary…")
        self.gist_progress.show()
        self.gist_retry_button.hide()
        self.summarize_further_button.setEnabled(False)
        self.copy_gist_button.setEnabled(False)
        self.save_gist_button.setEnabled(False)

    def _on_gist_ready(self, text: str) -> None:
        self._gist_running = False
        self._gist_backup = None
        self._pending_retry_level = ""
        self._gist_level = self._gist_request_level or "brief"
        self._gist_source = self._gist_request_source or self.english_editor.toPlainText()
        self.gist_editor.setPlaceholderText(_GIST_PLACEHOLDER)
        self._set_editor_text(self.gist_editor, text)
        self.gist_progress.hide()
        self.gist_level_choice.hide()
        self.use_level_button.hide()
        self._fit_gist_to_text()
        if self.english_editor.toPlainText() != self._gist_source:
            self._gist_state = "outdated"
            self.gist_retry_button.setText("Regenerate")
            self.gist_retry_button.show()
            self.statusBar().showMessage("The summary does not match the edited translation.")
        else:
            self._gist_state = "ready"
            self.gist_retry_button.setText("Retry")
            self.gist_retry_button.hide()
            self.statusBar().showMessage("Contextual summary ready.")
        self._refresh_gist_caption()
        if not self._busy:
            self._update_action_states()

    def _on_gist_failed(self, message: str) -> None:
        self._gist_running = False
        self.gist_editor.setPlaceholderText(_GIST_PLACEHOLDER)
        self.gist_progress.hide()
        if "English translation was kept" not in message:
            message = (
                "The contextual summary could not be written. The English translation was kept. "
                + message
            )
        if self._restore_gist_backup():
            self._pending_retry_level = self._gist_request_level or "brief"
            if self._gist_state != "outdated":
                self.gist_retry_button.setText("Retry")
                self.gist_caption.setText("The previous summary was kept.")
            self.gist_retry_button.show()
            self.statusBar().showMessage(message)
        else:
            self._pending_retry_level = self._gist_request_level or "brief"
            self._gist_state = "failed"
            self._gist_level = ""
            self.gist_level_label.setText("")
            self._set_editor_text(self.gist_editor, message)
            self.gist_caption.setText("Summary was not written")
            self.gist_retry_button.setText("Retry")
            self.gist_retry_button.show()
            self._fit_gist_to_text()
            self.statusBar().showMessage("The English translation was kept. The summary needs attention.")
        if not self._busy:
            self._update_action_states()

    def _on_gist_cancelled(self) -> None:
        self._gist_running = False
        self.gist_editor.setPlaceholderText(_GIST_PLACEHOLDER)
        self.gist_progress.hide()
        if self._restore_gist_backup():
            self._pending_retry_level = self._gist_request_level or "brief"
            if self._gist_state != "outdated":
                self.gist_retry_button.setText("Retry")
                self.gist_caption.setText("Summary was cancelled. The previous summary was kept.")
            self.gist_retry_button.show()
            self.statusBar().showMessage(
                "Contextual summary cancelled. The English translation was kept."
            )
        else:
            self._pending_retry_level = self._gist_request_level or "brief"
            self._gist_state = "cancelled"
            self._gist_level = ""
            self.gist_level_label.setText("")
            self._set_editor_text(
                self.gist_editor,
                "The contextual summary was cancelled. The English translation was kept.",
            )
            self.gist_caption.setText("Summary was cancelled")
            self.gist_retry_button.setText("Retry")
            self.gist_retry_button.show()
            self.statusBar().showMessage(
                "Contextual summary cancelled. The English translation was kept."
            )
        if not self._busy:
            self._update_action_states()

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
        self._sync_gist_freshness()
        self._update_action_states()

    def _sync_gist_freshness(self) -> None:
        """Mark a finished gist outdated when the English text is edited."""
        if self._gist_running or self._gist_state not in {"ready", "outdated"}:
            return
        if not self._gist_source:
            return
        if self.english_editor.toPlainText() == self._gist_source:
            if self._gist_state == "outdated":
                self._gist_state = "ready"
                if not self._pending_retry_level:
                    self.gist_retry_button.hide()
                self.gist_retry_button.setText("Retry")
                self._refresh_gist_caption()
            return
        self._gist_state = "outdated"
        self.gist_retry_button.setText("Regenerate")
        self.gist_retry_button.show()
        self._refresh_gist_caption()

    def _restore_gist_backup(self) -> bool:
        backup = self._gist_backup
        self._gist_backup = None
        if backup is None:
            return False
        level, text, source, state = backup
        self._gist_level = level
        self._gist_source = source
        self._gist_state = state if state in {"ready", "outdated"} else "ready"
        self._set_editor_text(self.gist_editor, text)
        if self.english_editor.toPlainText() != source:
            self._gist_state = "outdated"
            self.gist_retry_button.setText("Regenerate")
        self._refresh_gist_caption()
        self._fit_gist_to_text()
        return True

    def _refresh_gist_caption(self) -> None:
        if not self._gist_level or self._gist_state in {"empty", "failed", "cancelled"}:
            self.gist_level_label.setText("")
            if self._gist_state == "empty":
                self.gist_caption.setText("Read only")
            return
        label = level_label(self._gist_level)
        self.gist_level_label.setText(label)
        if self._gist_state == "outdated":
            self.gist_caption.setText(f"Outdated · {label}")
        else:
            self.gist_caption.setText(f"{label} · read only")
        nxt = next_summary_level(self._gist_level)
        if nxt is None:
            self.summarize_further_button.setToolTip(
                "Expanded is the longest summary. Choose Brief, Detailed, or Expanded to regenerate."
            )
        else:
            self.summarize_further_button.setToolTip(
                f"Write a {level_label(nxt).lower()} summary from the full English translation."
            )

    def _reset_gist(self) -> None:
        self._gist_state = "empty"
        self._gist_running = False
        self._gist_level = ""
        self._gist_source = ""
        self._gist_request_level = "brief"
        self._gist_request_source = ""
        self._gist_backup = None
        self._pending_retry_level = ""
        self.gist_editor.setPlaceholderText(_GIST_PLACEHOLDER)
        self.gist_editor.clear()
        self.gist_level_label.setText("")
        self.gist_caption.setText("Read only")
        self.gist_progress.hide()
        self.gist_retry_button.setText("Retry")
        self.gist_retry_button.hide()
        self.gist_level_choice.hide()
        self.use_level_button.hide()
        self._fit_gist_to_text()

    def _fit_gist_to_text(self) -> None:
        """Give a longer summary more of the vertical splitter, down to a minimum."""
        text = self.gist_editor.toPlainText()
        lines = text.count("\n") + (1 if text else 0)
        wanted = min(420, max(180, 24 * min(max(lines, 1), 14) + 88))
        sizes = self.detail_splitter.sizes()
        total = sum(sizes) or self.detail_splitter.height() or 640
        gist = min(wanted, max(180, total - 220))
        english = max(220, total - gist)
        self.detail_splitter.setSizes([english, gist])

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
        has_gist = self._gist_state in {"ready", "outdated"} and bool(self.gist_editor.toPlainText().strip())
        has_any = bool(
            self.urdu_editor.toPlainText()
            or self.english_editor.toPlainText()
            or self.gist_editor.toPlainText()
        )
        self.translate_button.setEnabled(has_source)
        self.clear_button.setEnabled(has_any)
        self.copy_button.setEnabled(has_translation)
        self.save_button.setEnabled(has_translation)
        self.export_button.setEnabled(has_translation)
        self.copy_gist_button.setEnabled(has_gist)
        self.save_gist_button.setEnabled(has_gist)
        self.summarize_further_button.setEnabled(has_gist and has_translation)
        self.use_level_button.setEnabled(has_translation)
        self.gist_retry_button.setEnabled(
            has_translation
            and (
                self._gist_state in {"failed", "cancelled", "outdated"}
                or bool(self._pending_retry_level)
            )
        )

    def _set_busy(self, busy: bool, *, label: str = "Translating…") -> None:
        self._busy = busy
        self.translate_button.setText(label if busy else "Translate")
        self.translate_button.setEnabled(not busy)
        self.open_button.setEnabled(not busy)
        self.clear_button.setEnabled(not busy)
        self.history_button.setEnabled(not busy)
        if busy:
            self.progress.show()
            self.copy_gist_button.setEnabled(False)
            self.save_gist_button.setEnabled(False)
            self.summarize_further_button.setEnabled(False)
            self.use_level_button.setEnabled(False)
            self.gist_retry_button.setEnabled(False)
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
