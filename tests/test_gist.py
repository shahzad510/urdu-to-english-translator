"""The contextual summary is a second output and does not replace the translation."""

import json
import os
import time
from pathlib import Path

import pytest
from docx import Document

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication, QPalette, QTextCursor  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QFileDialog, QLabel  # noqa: E402

from urdu_translator.documents import write_translation_docx  # noqa: E402
from urdu_translator.errors import TranslationCancelled, TranslationFailedError  # noqa: E402
from urdu_translator.gui.appearance import EDITOR_BACKGROUND, EDITOR_TEXT  # noqa: E402
from urdu_translator.gui.main_window import MainWindow  # noqa: E402
from urdu_translator.translation.backends.gemma import GemmaEngine, _settings  # noqa: E402
from urdu_translator.translation.backends.llama_server import owned_process_pid, reset_for_tests  # noqa: E402
from urdu_translator.translation.engine import TranslationEngine  # noqa: E402
from urdu_translator.translation.gist import (  # noqa: E402
    FINAL_SYSTEM,
    brief_summary_is_too_long,
    count_sentences,
    count_words,
    next_summary_level,
    summarize_english,
    system_prompt,
)
from urdu_translator.translation.package import ModelPackage  # noqa: E402
from urdu_translator.translation.registry import register_backend, unregister_backend  # noqa: E402
from urdu_translator.translation.service import produce_document_outputs  # noqa: E402
from urdu_translator.translation.terminology import Terminology  # noqa: E402

REPORTED = "Ahmed reportedly claimed that the road might be closed."
FINAL_GIST = (
    "Ahmed, Bilal, and Sheikh discussed Karachi, Lahore, and Quetta. "
    "Ahmed reportedly claimed that the road might be closed."
)


@pytest.fixture(scope="module")
def qapp():
    application = QApplication.instance()
    if application is None:
        application = QApplication([])
    return application


def _wait_until(qapp, predicate, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        qapp.processEvents()
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("Timed out waiting for the window to update.")


def _package(name: str = "Echo") -> ModelPackage:
    return ModelPackage(
        name=name,
        backend="echo",
        directory=Path("."),
        source_language="ur",
        target_language="en",
        is_default=True,
        options={},
    )


class _ChunkEngine(TranslationEngine):
    def __init__(self, replies: list[list[str]] | None = None) -> None:
        super().__init__(_package("Chunk"))
        self.replies = replies or []
        self.events: list[object] = []
        self.max_chunk_chars = 12
        self.overlap_lines = 0

    def translate_batch(self, texts: list[str]) -> list[str]:
        raise AssertionError("Grouped translation should not call translate_batch.")

    def translate_chunk(self, lines: list[str], context: list[str], should_stop=None) -> list[str]:
        self.events.append(("chunk", list(lines)))
        if self.replies:
            return self.replies.pop(0)
        return [f"EN {line}" for line in lines]

    def summarize(self, english: str, progress=None, should_stop=None) -> str:
        self.events.append(("gist", english))
        if progress is not None:
            progress("Writing the contextual summary…")
        return "One contextual summary."


def _long_english() -> str:
    paragraphs = [
        f"Ahmed spoke in Karachi. {REPORTED} " + ("detail " * 20),
        "Bilal sent instructions from Lahore on 12 March. " + ("detail " * 20),
        "Sheikh described the meeting in Quetta. " + ("detail " * 20),
    ]
    return "\n\n".join(paragraphs)


def test_a_short_summary_is_one_request_and_keeps_the_model_text():
    seen: list[tuple[str, str]] = []

    def complete(system: str, user: str, should_stop=None) -> str:
        seen.append((system, user))
        return "```\nAhmed asked Bilal to meet at the North market on 12 March.\n```"

    text = "Ahmed: Meet Bilal at the North market on 12 March."
    progress: list[str] = []
    result = summarize_english(text, complete, progress=progress.append, max_chars=6000)
    assert result == "Ahmed asked Bilal to meet at the North market on 12 March."
    assert len(seen) == 1
    assert text in seen[0][1]
    assert "North market" in seen[0][1]
    assert "12 March" in seen[0][1]
    assert "sentence by sentence" in seen[0][0]
    assert progress == ["Writing the contextual summary…"]


def test_multiple_speakers_locations_and_uncertainty_stay_in_one_summary():
    seen: list[tuple[str, str]] = []

    def complete(system: str, user: str, should_stop=None) -> str:
        seen.append((system, user))
        return (
            "Ahmed, Bilal, and Sheikh discussed Karachi and Lahore. "
            "Ahmed reportedly claimed that Bilal might travel to Lahore."
        )

    text = "\n".join(
        [
            "Ahmed: I am in Karachi.",
            "Bilal: Send the papers to Lahore.",
            "Sheikh: Ahmed reportedly claimed that Bilal might travel to Lahore.",
        ]
    )
    result = summarize_english(text, complete, max_chars=6000)
    assert len(seen) == 1
    system, user = seen[0]
    for name in ("Ahmed", "Bilal", "Sheikh", "Karachi", "Lahore"):
        assert name in user
    assert "Ahmed reportedly claimed that Bilal might travel to Lahore." in user
    assert "established fact" in system
    assert "threat rating" in system.lower()
    assert "prediction" in system.lower()
    assert "recommendation" in system.lower()
    assert "Islamabad" not in user
    assert "weapon" not in user.lower()
    assert result == (
        "Ahmed, Bilal, and Sheikh discussed Karachi and Lahore. "
        "Ahmed reportedly claimed that Bilal might travel to Lahore."
    )
    assert "threat" not in result.lower()


def test_a_long_conversation_becomes_one_gist_not_one_per_part():
    calls: list[tuple[str, str]] = []

    def complete(system: str, user: str, should_stop=None) -> str:
        calls.append((system, user))
        if "separate final summary" in system:
            found = [
                token
                for token in ("Ahmed", "Bilal", "Sheikh", "Karachi", "Lahore", "Quetta", "12 March", REPORTED)
                if token in user
            ]
            return "Noted " + "; ".join(found)
        return FINAL_GIST

    progress: list[str] = []
    result = summarize_english(_long_english(), complete, progress=progress.append, max_chars=400)
    partials = [user for system, user in calls if "separate final summary" in system]
    finals = [user for system, user in calls if system == FINAL_SYSTEM]
    assert len(partials) >= 2
    assert len(finals) == 1
    assert result == FINAL_GIST
    assert "Part 1:" in finals[0]
    assert "Noted " in finals[0]
    assert "Karachi" in finals[0]
    assert "Quetta" in finals[0]
    assert any(REPORTED in user for _system, user in calls)
    assert any(message.startswith("Summarising part ") for message in progress)
    assert "Combining the section summaries…" in progress
    joined_partials = "\n".join(partials)
    assert result != joined_partials


def test_summary_cancellation_stops_before_a_final_gist():
    def complete(system: str, user: str, should_stop=None) -> str:
        raise AssertionError("The model should not be called after cancellation.")

    with pytest.raises(TranslationCancelled, match="cancelled"):
        summarize_english("Ahmed is in Karachi.", complete, should_stop=lambda: True)

    calls = {"n": 0}

    def stopping() -> bool:
        return calls["n"] >= 1

    def once(system: str, user: str, should_stop=None) -> str:
        calls["n"] += 1
        return "Part note about Ahmed."

    with pytest.raises(TranslationCancelled):
        summarize_english(_long_english(), once, should_stop=stopping, max_chars=400)
    assert calls["n"] == 1


def test_gist_runs_after_the_translation_is_assembled():
    engine = _ChunkEngine([["Hello from Karachi"], ["Yes, on 12 March"]])
    published: list[str] = []

    def published_text(result) -> None:
        published.append(result.text)
        assert engine.events[-1][0] == "chunk"
        assert not any(event[0] == "gist" for event in engine.events if isinstance(event, tuple))

    source = "احمد: سلام\n\nبلال: جی"
    outputs = produce_document_outputs(source, lambda: engine, on_translated=published_text)
    assert published == [outputs.translation.text]
    assert outputs.gist == "One contextual summary."
    assert outputs.gist_error == ""
    assert outputs.gist_cancelled is False
    assert engine.events[-1] == ("gist", outputs.translation.text)
    assert engine.events[-1][1] == published[0]
    assert "Ahmed:" in outputs.translation.text
    assert "Bilal:" in outputs.translation.text
    assert "Karachi" in outputs.translation.text
    assert "12 March" in outputs.translation.text
    assert all(event == "chunk" or (isinstance(event, tuple) and event[0] == "chunk") for event in engine.events[:-1])


def test_several_speakers_are_summarised_once():
    engine = _ChunkEngine()
    engine.max_chunk_chars = 500
    source = "احمد: سلام\nبلال: کراچی\nشیخ: لاہور"
    outputs = produce_document_outputs(source, lambda: engine)
    gists = [event for event in engine.events if isinstance(event, tuple) and event[0] == "gist"]
    chunks = [event for event in engine.events if isinstance(event, tuple) and event[0] == "chunk"]
    assert len(chunks) == 1
    assert len(gists) == 1
    english = gists[0][1]
    assert english == outputs.translation.text
    assert "Ahmed:" in english
    assert "Bilal:" in english
    assert "Sheikh:" in english
    assert outputs.gist == "One contextual summary."


def test_a_summary_failure_keeps_the_translation():
    class Broken(TranslationEngine):
        def __init__(self) -> None:
            super().__init__(_package())

        def translate_batch(self, texts: list[str]) -> list[str]:
            return ["Hello Ahmed in Karachi."]

        def summarize(self, english: str, progress=None, should_stop=None) -> str:
            raise TranslationFailedError("model stopped")

    outputs = produce_document_outputs("سلام", lambda: Broken())
    assert outputs.translation.text == "Hello Ahmed in Karachi."
    assert outputs.gist == ""
    assert outputs.gist_cancelled is False
    assert "model stopped" in outputs.gist_error
    assert "English translation was kept" in outputs.gist_error


def test_cancelling_the_summary_keeps_the_translation():
    class Stopping(TranslationEngine):
        def __init__(self) -> None:
            super().__init__(_package())

        def translate_batch(self, texts: list[str]) -> list[str]:
            return ["Hello Ahmed."]

        def summarize(self, english: str, progress=None, should_stop=None) -> str:
            raise TranslationCancelled("The contextual summary was cancelled.")

    outputs = produce_document_outputs("سلام", lambda: Stopping())
    assert outputs.translation.text == "Hello Ahmed."
    assert outputs.gist == ""
    assert outputs.gist_error == ""
    assert outputs.gist_cancelled is True


def test_cancelling_translation_does_not_start_a_summary():
    class Stopping(TranslationEngine):
        def __init__(self) -> None:
            super().__init__(_package())
            self.summaries = 0

        def translate_batch(self, texts: list[str]) -> list[str]:
            raise TranslationCancelled("Translation was cancelled.")

        def translate_chunk(self, lines: list[str], context: list[str], should_stop=None) -> list[str]:
            raise TranslationCancelled("Translation was cancelled.")

        def summarize(self, english: str, progress=None, should_stop=None) -> str:
            self.summaries += 1
            return "should not run"

    engine = Stopping()
    with pytest.raises(TranslationCancelled):
        produce_document_outputs("احمد: سلام", lambda: engine)
    assert engine.summaries == 0


def test_gemma_summary_reuses_the_translation_completer(tmp_path: Path):
    calls: list[str] = []

    def complete(system: str, user: str, should_stop=None) -> str:
        calls.append(user)
        assert "Ahmed met Bilal in Karachi." in user
        assert should_stop is not None
        return "Ahmed met Bilal in Karachi."

    package = ModelPackage(
        name="Gemma 4 E4B",
        backend="gemma",
        directory=tmp_path,
        source_language="ur",
        target_language="en",
        is_default=True,
        options={"context_length": 8192, "max_new_tokens": 2048},
    )
    try:
        reset_for_tests()
        engine = GemmaEngine(package, Terminology([]), complete, **_settings(package))
        assert engine.summarize("Ahmed met Bilal in Karachi.", should_stop=lambda: False) == (
            "Ahmed met Bilal in Karachi."
        )
        assert len(calls) == 1
        assert owned_process_pid() is None
    finally:
        reset_for_tests()


def test_docx_export_contains_urdu_english_and_the_gist(tmp_path: Path):
    path = tmp_path / "briefing.docx"
    write_translation_docx(
        path,
        urdu="احمد: سلام",
        english="Ahmed: Hello there.\n\nThe meeting is in Karachi.",
        gist="Ahmed greeted the group.\n\nThe meeting is in Karachi.",
    )
    document = Document(str(path))
    texts = [paragraph.text for paragraph in document.paragraphs]
    assert texts == [
        "Original Urdu text",
        "احمد: سلام",
        "English translation",
        "Ahmed: Hello there.",
        "",
        "The meeting is in Karachi.",
        "Gist / Contextual Summary",
        "Ahmed greeted the group.",
        "",
        "The meeting is in Karachi.",
    ]
    assert document.paragraphs[0].runs[0].bold
    assert 'w:val="1"' in document.paragraphs[1]._p.xml
    assert 'w:val="0"' in document.paragraphs[3]._p.xml
    assert 'w:val="0"' in document.paragraphs[7]._p.xml


def _install_backend(name: str, factory) -> None:
    register_backend(name, factory)


def _window(tmp_path: Path, backend: str, factory) -> MainWindow:
    _install_backend(backend, factory)
    models = tmp_path / "models"
    package = models / "echo"
    package.mkdir(parents=True)
    (package / "engine.json").write_text(
        json.dumps({"name": "Echo", "backend": backend, "default": True}),
        encoding="utf-8",
    )
    return MainWindow(models_directory=models, history_database=tmp_path / "history.db")


def test_the_gist_panel_is_read_only_black_on_white_and_resizable(qapp, tmp_path: Path):
    window = MainWindow(models_directory=tmp_path / "models", history_database=tmp_path / "history.db")
    window.show()
    window.resize(1280, 860)
    qapp.processEvents()
    try:
        titles = [label.text() for label in window.findChildren(QLabel)]
        assert "Gist / Contextual Summary" in titles
        assert window.gist_editor.placeholderText() == (
            "Contextual summary will appear here after translation."
        )
        assert window.gist_editor.isReadOnly()
        assert window.gist_editor.minimumHeight() >= 100
        assert window.gist_editor.parent().minimumHeight() >= 160
        assert window.detail_splitter.orientation() == Qt.Orientation.Vertical
        assert window.detail_splitter.childrenCollapsible() is False
        assert window.gist_editor.layoutDirection() == Qt.LayoutDirection.LeftToRight
        text = window.gist_editor.viewport().palette().color(QPalette.ColorRole.Text).name().upper()
        background = window.gist_editor.viewport().palette().color(QPalette.ColorRole.Base).name().upper()
        assert text == EDITOR_TEXT == "#000000"
        assert background == EDITOR_BACKGROUND == "#FFFFFF"
        flags = window.gist_editor.textInteractionFlags()
        assert flags & Qt.TextInteractionFlag.TextSelectableByMouse
        assert flags & Qt.TextInteractionFlag.TextSelectableByKeyboard

        gist_point = window.gist_editor.mapTo(window, window.gist_editor.rect().center())
        english_point = window.english_editor.mapTo(window, window.english_editor.rect().center())
        urdu_point = window.urdu_editor.mapTo(window, window.urdu_editor.rect().center())
        assert gist_point.y() > english_point.y()
        assert gist_point.x() > urdu_point.x()

        window.detail_splitter.setSizes([320, 260])
        assert window.detail_splitter.sizes()[1] >= 160

        window.gist_editor.setPlainText("Short.")
        window._fit_gist_to_text()
        short = window.detail_splitter.sizes()[1]
        window.gist_editor.setPlainText("\n".join(["A longer summary line about the meeting."] * 12))
        window._fit_gist_to_text()
        assert window.detail_splitter.sizes()[1] > short

        window.gist_editor.setPlainText("Ahmed met Bilal in Karachi.")
        window.gist_editor.setFocus()
        QTest.keyClick(window.gist_editor, Qt.Key.Key_Z)
        QTest.keyClick(window.gist_editor, Qt.Key.Key_Backspace)
        assert window.gist_editor.toPlainText() == "Ahmed met Bilal in Karachi."
        cursor = window.gist_editor.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        window.gist_editor.setTextCursor(cursor)
        assert "Karachi" in window.gist_editor.textCursor().selectedText()
    finally:
        window.close()


def test_the_window_shows_the_gist_without_changing_the_translation(qapp, tmp_path: Path):
    class SummaryEngine(TranslationEngine):
        def __init__(self, package: ModelPackage) -> None:
            super().__init__(package)
            self.english = ""

        def translate_batch(self, texts: list[str]) -> list[str]:
            return [f"[{text}]" for text in texts]

        def summarize(self, english: str, progress=None, should_stop=None) -> str:
            self.english = english
            if progress is not None:
                progress("Writing the contextual summary…")
            return "Ahmed was in Karachi."

    window = _window(tmp_path, "gist-summary", SummaryEngine)
    try:
        urdu = "احمد: سلام"
        window.urdu_editor.setPlainText(urdu)
        window.translate()
        _wait_until(
            qapp,
            lambda: window._gist_state == "ready" and not window._busy,
        )
        english = window.english_editor.toPlainText()
        assert english == "Ahmed: [سلام]"
        assert window.urdu_editor.toPlainText() == urdu
        assert window.gist_editor.toPlainText() == "Ahmed was in Karachi."
        assert window.gist_level_label.text() == "Brief"
        assert window.summarize_further_button.text() == "Summarize Further"
        assert window.gist_editor.isReadOnly()
        assert window.gist_progress.isVisible() is False
        assert window.copy_gist_button.isEnabled()
        assert window.save_gist_button.isEnabled()
        assert window.banner.isVisible() is False
    finally:
        window.close()
        unregister_backend("gist-summary")


def test_gist_failure_leaves_the_translation_and_offers_retry(qapp, tmp_path: Path):
    class Flaky(TranslationEngine):
        attempts = 0

        def __init__(self, package: ModelPackage) -> None:
            super().__init__(package)

        def translate_batch(self, texts: list[str]) -> list[str]:
            return ["Hello Ahmed in Karachi."]

        def summarize(self, english: str, progress=None, should_stop=None) -> str:
            Flaky.attempts += 1
            if Flaky.attempts == 1:
                raise TranslationFailedError("model stopped")
            return "Ahmed was in Karachi."

    window = _window(tmp_path, "gist-flaky", Flaky)
    window.show()
    try:
        window.urdu_editor.setPlainText("سلام")
        window.translate()
        _wait_until(qapp, lambda: window._gist_state == "failed" and not window._busy)
        english = window.english_editor.toPlainText()
        assert english == "Hello Ahmed in Karachi."
        assert "model stopped" in window.gist_editor.toPlainText()
        assert "English translation was kept" in window.gist_editor.toPlainText()
        assert window.gist_retry_button.isHidden() is False
        assert window.gist_retry_button.isEnabled()
        assert window.copy_gist_button.isEnabled() is False
        assert window.banner.isVisible() is False

        window.gist_retry_button.click()
        _wait_until(qapp, lambda: window._gist_state == "ready" and not window._busy)
        assert window.english_editor.toPlainText() == english
        assert window.urdu_editor.toPlainText() == "سلام"
        assert window.gist_editor.toPlainText() == "Ahmed was in Karachi."
        assert window.gist_retry_button.isHidden()
    finally:
        window.close()
        unregister_backend("gist-flaky")


def test_cancelling_the_gist_keeps_the_english_panel(qapp, tmp_path: Path):
    class Waiting(TranslationEngine):
        def __init__(self, package: ModelPackage) -> None:
            super().__init__(package)

        def translate_batch(self, texts: list[str]) -> list[str]:
            return ["Hello Ahmed."]

        def summarize(self, english: str, progress=None, should_stop=None) -> str:
            deadline = time.time() + 5
            while time.time() < deadline:
                if should_stop is not None and should_stop():
                    raise TranslationCancelled("The contextual summary was cancelled.")
                time.sleep(0.01)
            raise AssertionError("The summary was not cancelled.")

    window = _window(tmp_path, "gist-cancel", Waiting)
    window.show()
    try:
        window.urdu_editor.setPlainText("سلام")
        window.translate()
        _wait_until(qapp, lambda: window.english_editor.toPlainText() == "Hello Ahmed.")
        assert window._thread is not None
        window._thread.requestInterruption()
        _wait_until(qapp, lambda: window._gist_state == "cancelled" and not window._busy)
        assert window.english_editor.toPlainText() == "Hello Ahmed."
        assert window.urdu_editor.toPlainText() == "سلام"
        assert "cancelled" in window.gist_editor.toPlainText().lower()
        assert window.gist_retry_button.isHidden() is False
    finally:
        if window._thread is not None and window._thread.isRunning():
            window._thread.requestInterruption()
            window._thread.wait(2000)
        window.close()
        unregister_backend("gist-cancel")


def test_copy_and_txt_export_use_only_the_gist(qapp, tmp_path: Path, monkeypatch):
    window = MainWindow(models_directory=tmp_path / "models", history_database=tmp_path / "history.db")
    destination = tmp_path / "gist.txt"
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: (str(destination), "Text files (*.txt)"),
    )
    try:
        window.urdu_editor.setPlainText("سلام")
        window.english_editor.setPlainText("Hello Ahmed.")
        window._gist_state = "ready"
        window.gist_editor.setPlainText("Ahmed said hello.")
        window._update_action_states()
        window.copy_gist()
        assert QGuiApplication.clipboard().text() == "Ahmed said hello."
        window.save_gist()
        assert destination.read_text(encoding="utf-8") == "Ahmed said hello."
        assert "سلام" not in destination.read_text(encoding="utf-8")
        assert "Hello Ahmed." not in destination.read_text(encoding="utf-8")
    finally:
        window.close()


def test_the_window_exports_all_three_sections(qapp, tmp_path: Path, monkeypatch):
    window = MainWindow(models_directory=tmp_path / "models", history_database=tmp_path / "history.db")
    destination = tmp_path / "translation.docx"
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: (str(destination), "Word documents (*.docx)"),
    )
    try:
        window.urdu_editor.setPlainText("احمد: سلام")
        window.english_editor.setPlainText("Ahmed: Hello.")
        window._gist_state = "ready"
        window.gist_editor.setPlainText("Ahmed said hello in Karachi.")
        window.export_docx()
        document = Document(str(destination))
        texts = [paragraph.text for paragraph in document.paragraphs]
        assert "Original Urdu text" in texts
        assert "احمد: سلام" in texts
        assert "English translation" in texts
        assert "Ahmed: Hello." in texts
        assert "Gist / Contextual Summary" in texts
        assert "Ahmed said hello in Karachi." in texts
    finally:
        window.close()


_BRIEF = (
    "Ahmed asked Bilal to meet at the North market in Karachi on twelve March. "
    "Sheikh reported that the road might be closed before the group travelled there. "
    "The notes cover the meeting plan and that reported closure."
)


def test_the_default_gist_is_a_brief_summary_of_the_whole_text():
    seen: list[tuple[str, str]] = []
    too_long = " ".join(["Ahmed added another reported detail about the meeting."] * 6)

    def complete(system: str, user: str, should_stop=None) -> str:
        seen.append((system, user))
        if len(seen) == 1:
            return too_long
        return _BRIEF

    text = "Ahmed opened in Karachi.\n\nSheikh closed the exchange in Quetta."
    result = summarize_english(text, complete)
    assert brief_summary_is_too_long(too_long)
    assert not brief_summary_is_too_long(_BRIEF)
    assert 2 <= count_sentences(result) <= 3
    assert 35 <= count_words(result) <= 55
    assert result == _BRIEF
    assert len(seen) == 2
    assert seen[0][0] == system_prompt("brief") == FINAL_SYSTEM
    assert "2 or 3" in seen[0][0]
    assert "35 to 55" in seen[0][0]
    assert "not only the last section" in seen[0][1]
    assert text in seen[0][1]
    assert text in seen[1][1]
    assert "Karachi" in seen[0][1] and "Quetta" in seen[0][1]
    assert "Islamabad" not in seen[0][1]
    assert "invented facts" in seen[0][0]


def test_longer_levels_are_targets_and_still_use_the_full_text():
    source = "Ahmed opened in Karachi.\n\nSheikh closed the exchange in Quetta."
    long_reply = " ".join(["Ahmed and Sheikh discussed the reported plan in detail."] * 12)
    for level, phrase in (("detailed", "70 to 100"), ("expanded", "120 to 180")):
        seen: list[tuple[str, str]] = []

        def complete(system: str, user: str, should_stop=None) -> str:
            seen.append((system, user))
            return long_reply

        result = summarize_english(source, complete, level=level)
        assert len(seen) == 1
        assert result == long_reply
        assert phrase in seen[0][0]
        assert "not a rigid limit" in seen[0][0]
        assert "not only the last section" in seen[0][1]
        assert source in seen[0][1]
        assert "Karachi" in seen[0][1] and "Quetta" in seen[0][1]
        assert "Islamabad" not in seen[0][1]
        assert "invented facts" in seen[0][0]


def test_a_long_document_is_still_summarised_as_one_whole():
    calls: list[tuple[str, str]] = []

    def complete(system: str, user: str, should_stop=None) -> str:
        calls.append((system, user))
        if "separate final summary" in system:
            found = [token for token in ("Ahmed", "Karachi", "Quetta", "Lahore", "12 March") if token in user]
            return "Noted " + " ".join(found)
        return "One summary of the whole."

    result = summarize_english(_long_english(), complete, level="detailed", max_chars=400)
    finals = [(system, user) for system, user in calls if system == system_prompt("detailed")]
    assert len(finals) == 1
    assert result == "One summary of the whole."
    assert "70 to 100" in finals[0][0]
    assert "not only the last section" in finals[0][1]
    assert "Karachi" in finals[0][1]
    assert "Quetta" in finals[0][1]
    assert "12 March" in finals[0][1]


def test_summary_levels_do_not_expand_forever():
    assert next_summary_level("brief") == "detailed"
    assert next_summary_level("detailed") == "expanded"
    assert next_summary_level("expanded") is None
    assert next_summary_level("expanded") is None


def test_docx_records_the_selected_summary_level(tmp_path: Path):
    path = tmp_path / "levels.docx"
    write_translation_docx(
        path,
        urdu="سلام",
        english="Hello from Karachi.",
        gist="Ahmed was in Karachi.",
        gist_level="Detailed",
    )
    texts = [paragraph.text for paragraph in Document(str(path)).paragraphs]
    assert "Gist / Contextual Summary" in texts
    assert "Summary level: Detailed" in texts
    assert "Ahmed was in Karachi." in texts


def test_summarize_further_uses_the_full_translation_and_stops_at_expanded(qapp, tmp_path: Path):
    calls: list[tuple[str, str]] = []

    class LevelEngine(TranslationEngine):
        def __init__(self, package: ModelPackage) -> None:
            super().__init__(package)

        def translate_batch(self, texts: list[str]) -> list[str]:
            return list(texts)

        def summarize(self, english: str, progress=None, should_stop=None, level: str = "brief") -> str:
            calls.append((level, english))
            return f"{level} summary"

    window = _window(tmp_path, "gist-levels", LevelEngine)
    source = "Ahmed met Bilal in Karachi. Sheikh mentioned Lahore and a reported road closure."
    try:
        window.urdu_editor.setPlainText("سلام")
        window.english_editor.setPlainText(source)
        window._gist_state = "ready"
        window._gist_level = "brief"
        window._gist_source = source
        window.gist_editor.setPlainText("Ahmed and Bilal discussed Karachi and Lahore.")
        window._update_action_states()

        window.summarize_further()
        _wait_until(qapp, lambda: len(calls) == 1 and not window._busy)
        assert calls[0] == ("detailed", source)
        assert window.english_editor.toPlainText() == source
        assert window.urdu_editor.toPlainText() == "سلام"
        assert window.gist_level_label.text() == "Detailed"
        assert window.gist_editor.toPlainText() == "detailed summary"

        window.summarize_further()
        _wait_until(qapp, lambda: len(calls) == 2 and not window._busy)
        assert calls[1] == ("expanded", source)
        assert window.gist_level_label.text() == "Expanded"
        assert window.english_editor.toPlainText() == source

        window.summarize_further()
        qapp.processEvents()
        assert len(calls) == 2
        assert window._busy is False
        assert window.gist_level_choice.isHidden() is False
        assert [window.gist_level_choice.itemText(i) for i in range(window.gist_level_choice.count())] == [
            "Brief",
            "Detailed",
            "Expanded",
        ]

        window.gist_level_choice.setCurrentText("Brief")
        window.regenerate_selected_level()
        _wait_until(qapp, lambda: len(calls) == 3 and not window._busy)
        assert calls[2] == ("brief", source)
        assert window.gist_level_label.text() == "Brief"
        assert window.english_editor.toPlainText() == source
        assert window.urdu_editor.toPlainText() == "سلام"
    finally:
        window.close()
        unregister_backend("gist-levels")


def test_an_edited_translation_invalidates_the_gist_and_regeneration_uses_it(qapp, tmp_path: Path):
    calls: list[tuple[str, str]] = []

    class LevelEngine(TranslationEngine):
        def __init__(self, package: ModelPackage) -> None:
            super().__init__(package)

        def translate_batch(self, texts: list[str]) -> list[str]:
            return list(texts)

        def summarize(self, english: str, progress=None, should_stop=None, level: str = "brief") -> str:
            calls.append((level, english))
            return "Regenerated from the edited translation."

    window = _window(tmp_path, "gist-edit", LevelEngine)
    source = "Ahmed is in Karachi."
    try:
        window.english_editor.setPlainText(source)
        window.urdu_editor.setPlainText("سلام")
        window._gist_state = "ready"
        window._gist_level = "brief"
        window._gist_source = source
        window.gist_editor.setPlainText("Ahmed was in Karachi.")
        window._refresh_gist_caption()
        edited = "Ahmed is in Lahore."
        window.english_editor.setPlainText(edited)
        assert window._gist_state == "outdated"
        assert window.gist_level_label.text() == "Brief"
        assert window.gist_caption.text() == "Outdated · Brief"
        assert window.gist_editor.toPlainText() == "Ahmed was in Karachi."
        assert window.gist_retry_button.text() == "Regenerate"
        assert window.gist_retry_button.isHidden() is False
        assert window.english_editor.toPlainText() == edited

        window.gist_retry_button.click()
        _wait_until(qapp, lambda: len(calls) == 1 and not window._busy)
        assert calls[0] == ("brief", edited)
        assert window.english_editor.toPlainText() == edited
        assert window.urdu_editor.toPlainText() == "سلام"
        assert window.gist_editor.toPlainText() == "Regenerated from the edited translation."
        assert window._gist_state == "ready"
        assert window.gist_level_label.text() == "Brief"
    finally:
        window.close()
        unregister_backend("gist-edit")


def test_a_failed_longer_summary_keeps_the_translation_and_the_brief_gist(qapp, tmp_path: Path):
    class Boom(TranslationEngine):
        def __init__(self, package: ModelPackage) -> None:
            super().__init__(package)

        def translate_batch(self, texts: list[str]) -> list[str]:
            return list(texts)

        def summarize(self, english: str, progress=None, should_stop=None, level: str = "brief") -> str:
            raise TranslationFailedError("model stopped")

    window = _window(tmp_path, "gist-keep", Boom)
    source = "Ahmed is in Karachi."
    try:
        window.urdu_editor.setPlainText("سلام")
        window.english_editor.setPlainText(source)
        window._gist_state = "ready"
        window._gist_level = "brief"
        window._gist_source = source
        window.gist_editor.setPlainText("Ahmed was in Karachi.")
        window.summarize_further()
        _wait_until(qapp, lambda: not window._busy)
        assert window.english_editor.toPlainText() == source
        assert window.urdu_editor.toPlainText() == "سلام"
        assert window.gist_editor.toPlainText() == "Ahmed was in Karachi."
        assert window.gist_level_label.text() == "Brief"
        assert window.gist_retry_button.isHidden() is False
    finally:
        window.close()
        unregister_backend("gist-keep")
