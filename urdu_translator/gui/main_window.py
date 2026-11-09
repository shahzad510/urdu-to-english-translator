"""The Urdu and English window."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from PySide6.QtCore import QByteArray, QSettings, QSize, Qt, QTimer
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
    QSizePolicy,
    QPushButton,
    QRadioButton,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from urdu_translator.documents import read_document, write_docx, write_translation_docx, write_txt
from urdu_translator.errors import AppError
from urdu_translator.gui.appearance import apply_editor_colors, stylesheet
from urdu_translator.gui.editors import Editor, SourceEditor, configure_editor
from urdu_translator.gui.flow_layout import FlowLayout
from urdu_translator.gui.fonts import interface_font, urdu_font
from urdu_translator.gui.history_dialog import HistoryDialog
from urdu_translator.history.store import HistoryRecord, HistoryStore, readable_english
from urdu_translator.paths import database_path, models_dir, window_settings_path
from urdu_translator.translation.backends.llama_server import stop_owned_server
from urdu_translator.translation.loader import EngineStatus, inspect_engine
from urdu_translator.translation.gist import level_label
from urdu_translator.translation.service import TranslationResult
from urdu_translator.workers.gist_worker import GistWorker
from urdu_translator.workers.translate_worker import TranslateWorker

logger = logging.getLogger("urdu_translator.window")

_GIST_PLACEHOLDER = "Contextual summary will appear here after translation."
_GIST_WORKING = "Writing the contextual summary…"
_STATUS_CURRENT = "Up to date"
_STATUS_OUTDATED = "Translation edited — summary is outdated"
_STATUS_GENERATING = "Generating summary..."
_STATUS_FAILED = "Summary generation failed"
_SUMMARY_LEVELS = (("brief", "Brief"), ("detailed", "Detailed"), ("expanded", "Expanded"))


class _WrappingButtons(QWidget):
    """A button row that uses a second line instead of drawing past its parent."""

    def __init__(self, buttons: tuple[QPushButton, ...]) -> None:
        super().__init__()
        self._row = FlowLayout(self, spacing=8)
        for button in buttons:
            self._row.addWidget(button)
        policy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._row.heightForWidth(width)

    def minimumSizeHint(self) -> QSize:
        return self._row.minimumSize()

    def sizeHint(self) -> QSize:
        return self._row.sizeHint()


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
        self._placed = False
        self._pending_maximize = False
        self._sharing_details = False
        self._user_sized_details = False
        self._gist_state = "empty"
        self._gist_running = False
        self._gist_level = "brief"
        self._radio_level = "brief"
        self._gist_source = ""
        self._gist_request_level = "brief"
        self._gist_request_source = ""
        self._gist_backup: tuple[str, str, str, str] | None = None
        self._summaries: dict[str, tuple[str, str]] = {}

        self.setWindowTitle("Urdu → English")
        self.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint, True)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, True)
        self.setWindowFlag(Qt.WindowType.WindowSystemMenuHint, True)
        self.setMinimumSize(760, 640)
        self.resize(1200, 760)
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
        self.gist_editor.setMinimumHeight(100)
        self.urdu_editor.setMinimumHeight(80)
        self.english_editor.setMinimumHeight(80)
        for editor in (self.urdu_editor, self.english_editor, self.gist_editor):
            editor.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.gist_editor.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.gist_editor.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )

        self.open_button = QPushButton("Open")
        self.open_button.setShortcut(QKeySequence.StandardKey.Open)
        self.open_button.clicked.connect(self.open_document)

        self.translate_button = QPushButton("Translate")
        self.translate_button.setObjectName("PrimaryButton")
        self.translate_button.setShortcut(QKeySequence("Ctrl+Return"))
        self.translate_button.clicked.connect(self.translate)
        self.clear_button = QPushButton("Clear")
        self.clear_button.clicked.connect(self.clear_editors)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(14)
        source_column = self._build_source_column()
        source_column.setMinimumWidth(280)
        splitter.addWidget(source_column)
        self.detail_splitter = QSplitter(Qt.Orientation.Vertical)
        self.detail_splitter.setChildrenCollapsible(False)
        self.detail_splitter.setHandleWidth(14)
        self._english_panel = self._build_english_panel()
        self._gist_panel = self._build_gist_panel()
        self.detail_splitter.addWidget(self._english_panel)
        self.detail_splitter.addWidget(self._gist_panel)
        self.detail_splitter.setMinimumWidth(600)
        self.detail_splitter.splitterMoved.connect(self._note_detail_splitter_move)
        self.detail_splitter.setStretchFactor(0, 1)
        self.detail_splitter.setStretchFactor(1, 1)
        self.detail_splitter.setSizes([320, 320])
        for panel in (self._english_panel, self._gist_panel):
            panel.setMinimumHeight(panel.layout().minimumSize().height())
            panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
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

        self.setStatusBar(QStatusBar())
        self._build_status_widgets()
        self._mark_level_buttons()
        self._update_action_states()

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

        self.export_complete_button = QPushButton("Export Complete Document")
        self.export_complete_button.clicked.connect(self.export_docx)
        header.addWidget(self.export_complete_button)

        self.history_button = QPushButton("History")
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

    def _build_source_column(self) -> QWidget:
        column = QWidget()
        layout = QVBoxLayout(column)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self._build_panel(
            "Urdu Text",
            "Right to left",
            self.urdu_editor,
            object_name="Panel",
            corner=self.open_button,
        ), stretch=1)
        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addWidget(self.translate_button)
        actions.addWidget(self.clear_button)
        actions.addStretch(1)
        layout.addLayout(actions)
        return column

    def _button_row(self, *buttons: QPushButton) -> QWidget:
        return _WrappingButtons(buttons)

    def _build_english_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("EnglishPanel")
        panel.setMinimumHeight(140)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(6)

        title = QLabel("English Translation")
        title.setObjectName("PanelTitle")
        layout.addWidget(title)
        caption = QLabel("Left to right · editable")
        caption.setObjectName("PanelCaption")
        layout.addWidget(caption)
        layout.addWidget(self.english_editor, stretch=1)

        self.copy_translation_button = QPushButton("Copy Translation")
        self.copy_translation_button.setShortcut(QKeySequence("Ctrl+Shift+C"))
        self.copy_translation_button.clicked.connect(self.copy_translation)
        self.save_translation_button = QPushButton("Save Translation as TXT")
        self.save_translation_button.setShortcut(QKeySequence.StandardKey.Save)
        self.save_translation_button.clicked.connect(self.save_txt)
        self.export_translation_button = QPushButton("Export Translation as DOCX")
        self.export_translation_button.setShortcut(QKeySequence("Ctrl+Shift+E"))
        self.export_translation_button.clicked.connect(self.export_translation_docx)
        layout.addWidget(self._button_row(
            self.copy_translation_button,
            self.save_translation_button,
            self.export_translation_button,
        ))
        return panel

    def _build_gist_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("GistPanel")
        panel.setMinimumHeight(180)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        heading = QHBoxLayout()
        heading.setSpacing(8)
        label = QLabel("Gist / Contextual Summary")
        label.setObjectName("PanelTitle")
        heading.addWidget(label)
        heading.addStretch(1)
        self.gist_level_label = QLabel("Brief")
        self.gist_level_label.setObjectName("PanelTitle")
        heading.addWidget(self.gist_level_label)
        layout.addLayout(heading)

        self.gist_caption = QLabel("Read only")
        self.gist_caption.setObjectName("PanelCaption")
        layout.addWidget(self.gist_caption)

        self.level_buttons: dict[str, QRadioButton] = {}
        level_host = QWidget()
        levels = FlowLayout(level_host, spacing=8)
        for level, name in _SUMMARY_LEVELS:
            button = QRadioButton(name)
            button.setAutoExclusive(True)
            button.clicked.connect(lambda _checked=False, chosen=level: self.select_summary_level(chosen))
            self.level_buttons[level] = button
            levels.addWidget(button)
        layout.addWidget(level_host)

        self.regenerate_summary_button = QPushButton("Regenerate Summary")
        self.regenerate_summary_button.clicked.connect(self.regenerate_summary)
        self.summarize_further_button = QPushButton("Summarize Further")
        self.summarize_further_button.clicked.connect(self.summarize_further)
        self.return_to_brief_button = QPushButton("Return to Brief")
        self.return_to_brief_button.clicked.connect(self.return_to_brief)
        layout.addWidget(self._button_row(
            self.regenerate_summary_button,
            self.summarize_further_button,
            self.return_to_brief_button,
        ))

        status = QHBoxLayout()
        status.setSpacing(8)
        status_title = QLabel("Summary Status")
        status_title.setObjectName("PanelCaption")
        self.summary_status = QLabel("")
        self.summary_status.setObjectName("SummaryStatus")
        self.summary_status.setWordWrap(True)
        status.addWidget(status_title)
        status.addWidget(self.summary_status, stretch=1)
        layout.addLayout(status)

        layout.addWidget(self.gist_editor, stretch=1)
        self.gist_progress = QProgressBar()
        self.gist_progress.setRange(0, 0)
        self.gist_progress.setTextVisible(False)
        self.gist_progress.setFixedHeight(6)
        self.gist_progress.hide()
        layout.addWidget(self.gist_progress)

        self.copy_gist_button = QPushButton("Copy Gist")
        self.copy_gist_button.clicked.connect(self.copy_gist)
        self.save_gist_button = QPushButton("Save Gist as TXT")
        self.save_gist_button.clicked.connect(self.save_gist)
        self.export_gist_button = QPushButton("Export Gist as DOCX")
        self.export_gist_button.clicked.connect(self.export_gist_docx)
        layout.addWidget(self._button_row(
            self.copy_gist_button,
            self.save_gist_button,
            self.export_gist_button,
        ))
        return panel

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
        self.model_pill.setToolTip("")
        self.model_pill.setProperty("state", status.state)
        self._repolish(self.model_pill)

    def _apply_theme(self) -> None:
        """Paint the window and both editors. Direction settings are left alone."""
        self.setStyleSheet(stylesheet())
        apply_editor_colors(self.urdu_editor)
        apply_editor_colors(self.english_editor)
        apply_editor_colors(self.gist_editor)

    def show_model_details(self) -> None:
        """Show the model status, or the setup dialog when the model is missing."""
        status = self.refresh_model_status()
        if status.state != "ready":
            self.offer_model_setup()
            return
        self._show_banner(status.message, kind="info")

    def offer_model_setup(self) -> None:
        """Open the Gemma setup dialog when the offline model is not ready.

        A model that is already configured is reused. The dialog is the way to
        point at a USB copy. Translation is not described as ready until the
        model file can be read.
        """
        status = self.refresh_model_status()
        if status.state == "ready":
            self.statusBar().showMessage("AI Model Ready — Offline Mode")
            return
        from urdu_translator.gui.model_setup_dialog import ModelSetupDialog

        dialog = ModelSetupDialog(self)
        dialog.exec()
        status = self.refresh_model_status()
        if status.state == "ready":
            self.statusBar().showMessage("AI Model Ready — Offline Mode")
        else:
            self._show_banner(status.message, kind="warning")

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
        if not self._gist_is_exportable():
            self._show_banner("There is no contextual summary to copy.", kind="warning")
            return
        self._copy_editor(
            self.gist_editor,
            "Copied the contextual summary.",
            "There is no contextual summary to copy.",
        )

    def save_gist(self) -> None:
        """Save the contextual summary as a UTF-8 text file."""
        if not self._gist_is_exportable():
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

    def export_translation_docx(self) -> None:
        """Export the English translation by itself."""
        self._export_editor(
            self.english_editor,
            title="Export English translation",
            default_name="translation.docx",
            file_filter="Word documents (*.docx)",
            suffix=".docx",
            writer=write_docx,
            empty_message="There is no English translation to save.",
        )

    def export_gist_docx(self) -> None:
        """Export the contextual summary by itself."""
        if not self._gist_is_exportable():
            self._show_banner("There is no contextual summary to save.", kind="warning")
            return
        self._export_editor(
            self.gist_editor,
            title="Export contextual summary",
            default_name="gist.docx",
            file_filter="Word documents (*.docx)",
            suffix=".docx",
            writer=write_docx,
            empty_message="There is no contextual summary to save.",
        )

    def select_summary_level(self, level: str) -> None:
        """Choose which standard level Regenerate Summary will write.

        Changing the radio does not call the model and does not replace the
        summary on screen.
        """
        if self._busy:
            self._mark_level_buttons()
            return
        self._radio_level = level if level in self.level_buttons else "brief"
        self._mark_level_buttons()
        self._update_action_states()

    def summarize_further(self) -> None:
        """Compress the current Brief into one ultra-brief summary.

        Detailed and Expanded are left untouched. A second click does nothing
        once Ultra-brief is already on screen.
        """
        if self._busy or self._gist_level == "ultra":
            return
        if self._radio_level != "brief" or self._gist_level != "brief":
            self.statusBar().showMessage("Select Brief before summarizing further.")
            return
        if self._gist_state != "ready":
            return
        english = self.english_editor.toPlainText()
        if not english.strip() or english != self._gist_source:
            return
        cached = self._summaries.get("brief")
        if cached is None or cached[0] != english:
            brief = self.gist_editor.toPlainText().strip()
            if not brief:
                return
            self._summaries["brief"] = (english, brief)
            cached = self._summaries["brief"]
        self._request_gist("ultra", payload=cached[1])

    def regenerate_summary(self) -> None:
        """Regenerate the selected radio level from the latest English translation."""
        if self._busy:
            return
        self._request_gist(self._radio_level or "brief")

    def return_to_brief(self) -> None:
        """Select Brief and show a current Brief summary, or write one."""
        if self._busy:
            return
        self._radio_level = "brief"
        self._mark_level_buttons()
        if not self.english_editor.toPlainText().strip():
            self._gist_level = "brief"
            self.gist_level_label.setText(level_label("brief"))
            return
        self._show_or_generate("brief", force=False)

    def _show_or_generate(self, level: str, *, force: bool) -> None:
        """Display a summary of the current English text, or write a new one.

        A stored summary is shown only when it was generated from the English
        text now in the editor. An older summary is not presented as current.
        """
        english = self.english_editor.toPlainText()
        cached = self._summaries.get(level)
        if not force and cached is not None and cached[0] == english and english.strip():
            self._gist_level = level
            self._gist_source = english
            self._gist_state = "ready"
            self._set_editor_text(self.gist_editor, cached[1])
            self._set_summary_status("current")
            self._refresh_gist_caption()
            self._fit_gist_to_text()
            self._update_action_states()
            return
        self._request_gist(level)

    def _request_gist(self, level: str, *, payload: str | None = None) -> None:
        """Summarise without changing the Urdu text or the English translation.

        ``payload`` is the text sent to the model. Standard levels send the
        full English translation. Ultra-brief sends the stored Brief only.
        """
        if self._busy:
            return
        english = self.english_editor.toPlainText()
        if not english.strip():
            self._show_banner("There is no English translation to summarise.", kind="warning")
            return
        text = english if payload is None else payload
        if not text.strip():
            self._show_banner("There is no English translation to summarise.", kind="warning")
            return
        previous_level = self._gist_level or "brief"
        if self._gist_is_exportable():
            self._gist_backup = (
                previous_level,
                self.gist_editor.toPlainText(),
                self._gist_source,
                self._gist_state,
            )
        else:
            self._gist_backup = None
        self._gist_request_level = level or "brief"
        self._gist_request_source = english
        self._gist_level = self._gist_request_level
        self._hide_banner()
        self._mark_level_buttons()
        self._set_summary_status("generating")
        self._set_busy(True, label="Summarising…")
        self.statusBar().showMessage("Writing the contextual summary…")
        worker = GistWorker(text, self.models_directory, self._gist_request_level)
        worker.gist_started.connect(self._on_gist_started)
        worker.ready.connect(self._on_gist_ready)
        worker.failed.connect(self._on_gist_failed)
        worker.cancelled.connect(self._on_gist_cancelled)
        worker.status_message.connect(self._on_status_message)
        worker.finished.connect(self._on_worker_finished)
        self._thread = worker
        worker.start()

    def _gist_is_exportable(self) -> bool:
        return self._gist_state in {"ready", "outdated"} and bool(self.gist_editor.toPlainText().strip())

    def export_docx(self) -> None:
        """Export the Urdu text, English translation, and contextual summary."""
        english = self.english_editor.toPlainText()
        if not english.strip():
            self._show_banner("There is no English translation to save.", kind="warning")
            return
        path, _selected = QFileDialog.getSaveFileName(
            self,
            "Export complete document",
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
        self._save_window_state()
        thread = self._thread
        if thread is not None and thread.isRunning():
            thread.requestInterruption()
            thread.wait(10000)
        if thread is None or not thread.isRunning():
            stop_owned_server()
        super().closeEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        if not self._user_sized_details:
            self._share_detail_height()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        self._enforce_layout_minimum()
        if self._placed:
            return
        self._placed = True
        if not self._restore_window_state():
            self._center_on_screen()
        self._clamp_to_available_screen()
        self._share_detail_height()
        if self._pending_maximize:
            self._pending_maximize = False
            self.showMaximized()

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
        self._set_summary_status("generating")
        self.gist_progress.show()
        self._set_summary_controls_enabled(False)

    def _on_gist_ready(self, text: str) -> None:
        self._gist_running = False
        self._gist_backup = None
        level = self._gist_request_level or "brief"
        source = self._gist_request_source or self.english_editor.toPlainText()
        if level != "ultra":
            self._summaries[level] = (source, text)
        self._gist_level = level
        self._gist_source = source
        self.gist_editor.setPlaceholderText(_GIST_PLACEHOLDER)
        self._set_editor_text(self.gist_editor, text)
        self.gist_progress.hide()
        self._fit_gist_to_text()
        if self.english_editor.toPlainText() != source:
            self._gist_state = "outdated"
            self._set_summary_status("outdated")
            self.statusBar().showMessage("The summary does not match the edited translation.")
        else:
            self._gist_state = "ready"
            self._set_summary_status("current")
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
        if self._restore_gist_backup(failed=True):
            self.statusBar().showMessage(message)
        else:
            self._gist_state = "failed"
            self._gist_level = self._gist_request_level or self._gist_level or "brief"
            self._set_editor_text(self.gist_editor, message)
            self.gist_caption.setText("Read only")
            self._set_summary_status("failed")
            self._mark_level_buttons()
            self._fit_gist_to_text()
            self.statusBar().showMessage("The English translation was kept. The summary needs attention.")
        if not self._busy:
            self._update_action_states()

    def _on_gist_cancelled(self) -> None:
        self._gist_running = False
        self.gist_editor.setPlaceholderText(_GIST_PLACEHOLDER)
        self.gist_progress.hide()
        if self._restore_gist_backup(failed=False):
            self.statusBar().showMessage(
                "Contextual summary cancelled. The English translation was kept."
            )
        else:
            self._gist_state = "cancelled"
            self._gist_level = self._gist_request_level or self._gist_level or "brief"
            self._set_editor_text(
                self.gist_editor,
                "The contextual summary was cancelled. The English translation was kept.",
            )
            self.gist_caption.setText("Read only")
            self._set_summary_status("")
            self._mark_level_buttons()
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
                self._set_summary_status("current")
                self._refresh_gist_caption()
            return
        self._gist_state = "outdated"
        self._set_summary_status("outdated")
        self._refresh_gist_caption()

    def _restore_gist_backup(self, *, failed: bool) -> bool:
        backup = self._gist_backup
        self._gist_backup = None
        if backup is None:
            return False
        level, text, source, state = backup
        self._gist_level = level or "brief"
        self._gist_source = source
        self._gist_state = state if state in {"ready", "outdated"} else "ready"
        self._set_editor_text(self.gist_editor, text)
        if self.english_editor.toPlainText() != source:
            self._gist_state = "outdated"
        if failed:
            self._set_summary_status("failed")
        elif self._gist_state == "outdated":
            self._set_summary_status("outdated")
        else:
            self._set_summary_status("current")
        self._refresh_gist_caption()
        self._fit_gist_to_text()
        return True

    def _refresh_gist_caption(self) -> None:
        self._mark_level_buttons()
        if self._gist_running:
            return
        self.gist_caption.setText("Read only")

    def _mark_level_buttons(self) -> None:
        radio = self._radio_level if self._radio_level in self.level_buttons else "brief"
        self._radio_level = radio
        shown = self._gist_level or radio
        self.gist_level_label.setText(level_label(shown))
        for level, button in self.level_buttons.items():
            button.blockSignals(True)
            button.setChecked(level == radio)
            button.blockSignals(False)

    def _set_summary_status(self, kind: str) -> None:
        labels = {
            "current": _STATUS_CURRENT,
            "outdated": _STATUS_OUTDATED,
            "generating": _STATUS_GENERATING,
            "failed": _STATUS_FAILED,
        }
        self.summary_status.setText(labels.get(kind, ""))

    def _reset_gist(self) -> None:
        self._gist_state = "empty"
        self._gist_running = False
        self._gist_level = "brief"
        self._radio_level = "brief"
        self._gist_source = ""
        self._gist_request_level = "brief"
        self._gist_request_source = ""
        self._gist_backup = None
        self._summaries = {}
        self.gist_editor.setPlaceholderText(_GIST_PLACEHOLDER)
        self.gist_editor.clear()
        self.gist_caption.setText("Read only")
        self.gist_progress.hide()
        self._set_summary_status("")
        self._mark_level_buttons()
        self._fit_gist_to_text()

    def _fit_gist_to_text(self) -> None:
        """Give a longer summary more of the vertical splitter, down to a minimum."""
        text = self.gist_editor.toPlainText()
        lines = text.count("\n") + (1 if text else 0)
        wanted = min(480, max(200, 20 * min(max(lines, 1), 14) + 140))
        sizes = self.detail_splitter.sizes()
        total = sum(sizes) or self.detail_splitter.height() or 640
        gist = min(wanted, max(180, total - 160))
        english = max(140, total - gist)
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
        self.copy_translation_button.setEnabled(has_translation)
        self.save_translation_button.setEnabled(has_translation)
        self.export_translation_button.setEnabled(has_translation)
        self.export_complete_button.setEnabled(has_translation)
        self.copy_gist_button.setEnabled(has_gist)
        self.save_gist_button.setEnabled(has_gist)
        self.export_gist_button.setEnabled(has_gist)
        brief_is_current = (
            has_translation
            and self._radio_level == "brief"
            and self._gist_level == "brief"
            and self._gist_state == "ready"
            and self.english_editor.toPlainText() == self._gist_source
            and bool(self.gist_editor.toPlainText().strip())
        )
        self.summarize_further_button.setEnabled(brief_is_current)
        self.regenerate_summary_button.setEnabled(has_translation)
        self.return_to_brief_button.setEnabled(has_translation)
        for button in self.level_buttons.values():
            button.setEnabled(True)

    def _set_summary_controls_enabled(self, enabled: bool) -> None:
        self.copy_gist_button.setEnabled(enabled)
        self.save_gist_button.setEnabled(enabled)
        self.export_gist_button.setEnabled(enabled)
        self.summarize_further_button.setEnabled(enabled)
        self.regenerate_summary_button.setEnabled(enabled)
        self.return_to_brief_button.setEnabled(enabled)
        for button in self.level_buttons.values():
            button.setEnabled(enabled)

    def _set_busy(self, busy: bool, *, label: str = "Translating…") -> None:
        self._busy = busy
        self.translate_button.setText(label if busy else "Translate")
        self.translate_button.setEnabled(not busy)
        self.open_button.setEnabled(not busy)
        self.clear_button.setEnabled(not busy)
        self.history_button.setEnabled(not busy)
        if busy:
            self.progress.show()
            self._set_summary_controls_enabled(False)
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

    def _note_detail_splitter_move(self, _position: int, _index: int) -> None:
        if self._sharing_details or not self._placed:
            return
        self._user_sized_details = True

    def _share_detail_height(self) -> None:
        """Give the English and summary editors the spare height in equal parts."""
        if self._sharing_details:
            return
        total = sum(self.detail_splitter.sizes())
        if total < 200:
            return
        english_min = self._english_panel.minimumHeight()
        gist_min = self._gist_panel.minimumHeight()
        english_chrome = max(40, english_min - self.english_editor.minimumHeight())
        gist_chrome = max(40, gist_min - self.gist_editor.minimumHeight())
        spare = total - english_chrome - gist_chrome
        each = max(self.gist_editor.minimumHeight(), spare // 2)
        gist = max(gist_min, min(total - english_min, gist_chrome + each))
        english = max(english_min, total - gist)
        gist = total - english
        if self.detail_splitter.sizes() == [english, gist]:
            return
        self._sharing_details = True
        try:
            self.detail_splitter.setSizes([english, gist])
        finally:
            self._sharing_details = False

    def _enforce_layout_minimum(self) -> None:
        """Stop the window shrinking until buttons are pushed outside it."""
        for panel in (self._english_panel, self._gist_panel):
            layout = panel.layout()
            if layout is None:
                continue
            needed = layout.minimumSize().height()
            if needed > panel.minimumHeight():
                panel.setMinimumHeight(needed)
        hint = self.minimumSizeHint()
        width = max(760, hint.width())
        height = max(640, hint.height())
        if self.minimumWidth() != width or self.minimumHeight() != height:
            self.setMinimumSize(width, height)

    def _window_settings(self) -> QSettings:
        return QSettings(str(window_settings_path()), QSettings.Format.IniFormat)

    def _restore_window_state(self) -> bool:
        """Return True when a saved size and position could be applied."""
        settings = self._window_settings()
        geometry = settings.value("geometry")
        if not isinstance(geometry, QByteArray) or geometry.isEmpty():
            return False
        if not self.restoreGeometry(geometry):
            return False
        maximized = settings.value("maximized", False)
        self._pending_maximize = str(maximized).lower() in {"true", "1", "yes"}
        return True

    def _save_window_state(self) -> None:
        settings = self._window_settings()
        settings.setValue("geometry", self.saveGeometry())
        settings.setValue("maximized", self.isMaximized())

    def _center_on_screen(self) -> None:
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        width = min(self.width(), area.width())
        height = min(self.height(), area.height())
        self.resize(width, height)
        frame = self.frameGeometry()
        frame.moveCenter(area.center())
        self.move(frame.topLeft())

    def _clamp_to_available_screen(self) -> None:
        """Keep the title bar on the current screen, including a restored position."""
        if self.isMaximized() or self.isFullScreen():
            return
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        width = min(max(self.width(), self.minimumWidth()), area.width())
        height = min(max(self.height(), self.minimumHeight()), area.height())
        if width != self.width() or height != self.height():
            self.resize(width, height)
        frame = self.frameGeometry()
        x = min(max(frame.x(), area.left()), max(area.left(), area.right() - frame.width() + 1))
        y = min(max(frame.y(), area.top()), max(area.top(), area.bottom() - 80))
        self.move(x, y)

    @staticmethod
    def _repolish(widget: QWidget) -> None:
        style = widget.style()
        style.unpolish(widget)
        style.polish(widget)
