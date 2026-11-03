"""SQLite history of completed translations."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class HistoryRecord:
    """One saved translation."""

    id: int
    source_text: str
    translated_text: str
    source_language: str
    target_language: str
    engine_name: str
    created_at: str
    contextual_text: str = ""
    contextual_engine: str = ""


class HistoryStore:
    """Append-only history stored in a local SQLite file.

    Each call opens its own connection, so the window thread can write a
    record after the background worker has finished.
    """

    def __init__(self, database_path: Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialise()

    def add(
        self,
        *,
        source_text: str,
        translated_text: str,
        engine_name: str,
        source_language: str = "ur",
        target_language: str = "en",
        contextual_text: str = "",
        contextual_engine: str = "",
    ) -> HistoryRecord:
        """Store a completed translation and return the saved row."""
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO translations (
                    source_text,
                    translated_text,
                    source_language,
                    target_language,
                    engine_name,
                    created_at,
                    contextual_text,
                    contextual_engine
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_text,
                    translated_text,
                    source_language,
                    target_language,
                    engine_name,
                    created_at,
                    contextual_text,
                    contextual_engine,
                ),
            )
            record_id = int(cursor.lastrowid)
        record = self.get(record_id)
        if record is None:
            raise sqlite3.Error("The history row could not be read after it was saved.")
        return record

    def get(self, record_id: int) -> HistoryRecord | None:
        """Return one record, or None when the id is unknown."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM translations WHERE id = ?",
                (record_id,),
            ).fetchone()
        if row is None:
            return None
        return _record_from_row(row)

    def list_recent(self, limit: int = 300) -> list[HistoryRecord]:
        """Return the newest records, newest first."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM translations
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [_record_from_row(row) for row in rows]

    def delete(self, record_id: int) -> None:
        """Remove one history row."""
        with self._connect() as connection:
            connection.execute("DELETE FROM translations WHERE id = ?", (record_id,))

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialise(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS translations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_text TEXT NOT NULL,
                    translated_text TEXT NOT NULL,
                    source_language TEXT NOT NULL,
                    target_language TEXT NOT NULL,
                    engine_name TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_translations_created_at
                ON translations (created_at DESC, id DESC)
                """
            )
            _add_column(connection, "contextual_text", "TEXT NOT NULL DEFAULT ''")
            _add_column(connection, "contextual_engine", "TEXT NOT NULL DEFAULT ''")


def readable_english(record: HistoryRecord) -> str:
    """Return the saved English, including an older contextual copy when it differs."""
    primary = record.translated_text
    extra = record.contextual_text.strip()
    if not extra or extra == primary.strip():
        return primary
    return (
        f"{primary.rstrip()}\n\n"
        "Earlier contextual translation:\n"
        f"{record.contextual_text.rstrip()}\n"
    )


def _add_column(connection: sqlite3.Connection, name: str, definition: str) -> None:
    existing = {str(row[1]) for row in connection.execute("PRAGMA table_info(translations)")}
    if name not in existing:
        connection.execute(f"ALTER TABLE translations ADD COLUMN {name} {definition}")


def _record_from_row(row: sqlite3.Row) -> HistoryRecord:
    keys = row.keys()
    return HistoryRecord(
        id=int(row["id"]),
        source_text=str(row["source_text"]),
        translated_text=str(row["translated_text"]),
        source_language=str(row["source_language"]),
        target_language=str(row["target_language"]),
        engine_name=str(row["engine_name"]),
        created_at=str(row["created_at"]),
        contextual_text=str(row["contextual_text"]) if "contextual_text" in keys else "",
        contextual_engine=str(row["contextual_engine"]) if "contextual_engine" in keys else "",
    )
