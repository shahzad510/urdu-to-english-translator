"""Dialog that lists translations saved in SQLite."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from urdu_translator.gui.appearance import DEFAULT_APPEARANCE, Appearance, stylesheet
from urdu_translator.gui.fonts import urdu_font
from urdu_translator.history.store import HistoryRecord, HistoryStore, readable_english


class HistoryDialog(QDialog):
    """Browse, restore, and delete saved translations."""

    def __init__(self, store: HistoryStore, parent=None, appearance: Appearance | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self.selected_record: HistoryRecord | None = None
        self.setObjectName("HistoryDialog")
        self.setWindowTitle("Translation history")
        self.resize(880, 520)
        self.setStyleSheet(stylesheet(appearance or DEFAULT_APPEARANCE))
        self._build()
        self.reload()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        heading = QLabel("Saved translations")
        heading.setObjectName("Title")
        layout.addWidget(heading)

        note = QLabel("Open a row to restore the Urdu text and the English translation.")
        note.setObjectName("Subtitle")
        layout.addWidget(note)

        self.empty_label = QLabel("No translations have been saved yet.")
        self.empty_label.setObjectName("EmptyHistory")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.empty_label)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["When", "Urdu", "English"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.doubleClicked.connect(lambda _index: self._open_selected())
        layout.addWidget(self.table, stretch=1)

        buttons = QHBoxLayout()
        self.open_button = QPushButton("Open")
        self.open_button.setObjectName("PrimaryButton")
        self.open_button.clicked.connect(self._open_selected)
        self.delete_button = QPushButton("Delete")
        self.delete_button.clicked.connect(self._delete_selected)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.reject)
        buttons.addWidget(self.open_button)
        buttons.addWidget(self.delete_button)
        buttons.addStretch(1)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

    def reload(self) -> None:
        """Refresh the table from the database."""
        records = self.store.list_recent()
        self.table.setRowCount(len(records))
        urdu = urdu_font(12)
        for row_index, record in enumerate(records):
            when = QTableWidgetItem(format_timestamp(record.created_at))
            when.setData(Qt.ItemDataRole.UserRole, record.id)
            source = QTableWidgetItem(one_line_preview(record.source_text))
            source.setFont(urdu)
            source.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            translation = QTableWidgetItem(_english_preview(record))
            self.table.setItem(row_index, 0, when)
            self.table.setItem(row_index, 1, source)
            self.table.setItem(row_index, 2, translation)
        has_rows = bool(records)
        self.table.setVisible(has_rows)
        self.empty_label.setVisible(not has_rows)
        self.open_button.setEnabled(has_rows)
        self.delete_button.setEnabled(has_rows)

    def _selected_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if item is None:
            return None
        value = item.data(Qt.ItemDataRole.UserRole)
        return int(value) if value is not None else None

    def _open_selected(self) -> None:
        record_id = self._selected_id()
        if record_id is None:
            return
        record = self.store.get(record_id)
        if record is None:
            self.reload()
            return
        self.selected_record = record
        self.accept()

    def _delete_selected(self) -> None:
        record_id = self._selected_id()
        if record_id is None:
            return
        answer = QMessageBox.question(
            self,
            "Delete translation",
            "Delete this saved translation?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.store.delete(record_id)
        self.reload()


def format_timestamp(value: str) -> str:
    """Show a stored UTC timestamp in the local timezone."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    return parsed.astimezone().strftime("%d %b %Y  %H:%M")


def _english_preview(record: HistoryRecord) -> str:
    preview = one_line_preview(record.translated_text)
    extra = record.contextual_text.strip()
    if extra and extra != record.translated_text.strip():
        return f"{preview} · earlier contextual saved"
    return preview


def one_line_preview(text: str, limit: int = 80) -> str:
    """First non-empty line, shortened so the history table stays one line high."""
    line = ""
    for raw in text.splitlines():
        if raw.strip():
            line = " ".join(raw.split())
            break
    if len(line) <= limit:
        return line
    return line[: limit - 1].rstrip() + "…"
