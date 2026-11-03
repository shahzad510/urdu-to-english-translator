"""SQLite history stores Urdu and English together."""

import sqlite3
from pathlib import Path

from urdu_translator.history.store import HistoryStore, readable_english


def test_history_round_trip(tmp_path: Path):
    store = HistoryStore(tmp_path / "history.db")
    saved = store.add(
        source_text="جمال :۔سلام",
        translated_text="Jamal: Hello",
        engine_name="Echo",
    )
    assert saved.id == 1
    assert saved.source_language == "ur"
    assert saved.target_language == "en"

    again = store.get(saved.id)
    assert again is not None
    assert again.source_text == "جمال :۔سلام"
    assert again.translated_text == "Jamal: Hello"

    newest = store.add(
        source_text="دوسرا",
        translated_text="Second",
        engine_name="Echo",
    )
    listed = store.list_recent()
    assert [record.id for record in listed] == [newest.id, saved.id]

    store.delete(saved.id)
    assert store.get(saved.id) is None
    assert [record.id for record in store.list_recent()] == [newest.id]
    assert saved.contextual_text == ""


def test_an_older_row_keeps_both_english_texts_readable(tmp_path: Path):
    store = HistoryStore(tmp_path / "history.db")
    saved = store.add(
        source_text="سلام",
        translated_text="Hello",
        engine_name="OPUS-MT",
        contextual_text="Peace be upon you",
        contextual_engine="IndicTrans2",
    )
    text = readable_english(saved)
    assert "Hello" in text
    assert "Peace be upon you" in text
    assert "Earlier contextual translation" in text
    same = store.add(source_text="سلام", translated_text="Hello", engine_name="Gemma")
    assert readable_english(same) == "Hello"


def test_an_older_history_file_gains_contextual_columns(tmp_path: Path):
    path = tmp_path / "history.db"
    connection = sqlite3.connect(path)
    connection.execute(
        """
        CREATE TABLE translations (
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
        INSERT INTO translations (
            source_text, translated_text, source_language, target_language, engine_name, created_at
        ) VALUES ('سلام', 'Hello', 'ur', 'en', 'Old', '2026-01-01T00:00:00+00:00')
        """
    )
    connection.commit()
    connection.close()

    store = HistoryStore(path)
    record = store.get(1)
    assert record is not None
    assert record.translated_text == "Hello"
    assert record.contextual_text == ""
    saved = store.add(
        source_text="سلام",
        translated_text="Hello again",
        engine_name="Echo",
        contextual_text="Hi there",
        contextual_engine="Context",
    )
    assert saved.contextual_text == "Hi there"
    assert saved.contextual_engine == "Context"
