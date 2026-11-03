"""Both modes keep the supplied conversation's shape."""

from pathlib import Path

from tests.test_transcript import CONVERSATION
from urdu_translator.translation.context import choose_contextual_line, needs_neighbor_context
from urdu_translator.translation.engine import TranslationEngine
from urdu_translator.translation.package import ModelPackage
from urdu_translator.translation.service import translate_both, translate_document


def _package(name: str) -> ModelPackage:
    return ModelPackage(
        name=name,
        backend="echo",
        directory=Path("."),
        source_language="ur",
        target_language="en",
        is_default=True,
        options={},
    )


class _Literal(TranslationEngine):
    def __init__(self) -> None:
        super().__init__(_package("Literal echo"))
        self.batches: list[list[str]] = []

    def translate_batch(self, texts: list[str]) -> list[str]:
        self.batches.append(list(texts))
        return [f"L:{text}" for text in texts]


class _Contextual(TranslationEngine):
    def __init__(self) -> None:
        super().__init__(_package("Contextual echo"))
        self.seen: list[tuple[str, str]] = []

    def translate_batch(self, texts: list[str]) -> list[str]:
        return [f"plain:{text}" for text in texts]

    def translate_in_context(self, texts: list[str], contexts: list[str]) -> list[str]:
        self.seen.extend(zip(contexts, texts, strict=True))
        return [f"C:{text}" for text in texts]


def test_the_supplied_conversation_keeps_its_shape_in_both_modes():
    literal = _Literal()
    contextual = _Contextual()
    result = translate_both(CONVERSATION, lambda: literal, lambda: contextual)

    for text in (result.literal.text, result.contextual.text):
        lines = text.splitlines()
        assert lines[0].startswith("احمد: ")
        assert lines[1].startswith("بلال: ")
        assert lines[2] == ""
        assert "ROC/ Area:" in lines
        assert "North market" in lines
        assert "N/H" in text
        assert "احمد:" not in " ".join(part for batch in literal.batches for part in batch)

    assert result.literal.text.splitlines()[0].startswith("احمد: L:")
    assert result.contextual.text.splitlines()[0].startswith("احمد: C:")
    assert result.contextual_note == ""
    assert contextual.seen[0][0] == ""
    assert contextual.seen[1][0] == contextual.seen[0][1]
    assert "ROC/ Area:" not in [text for _previous, text in contextual.seen]
    assert "North market" not in [text for _previous, text in contextual.seen]


def test_literal_mode_does_not_send_the_previous_line():
    engine = _Contextual()

    def load() -> TranslationEngine:
        return engine

    result = translate_document("احمد: ہاں\nبلال: ٹھیک ہے", load, mode="literal")
    assert "C:" not in result.text
    assert "plain:" in result.text
    assert engine.seen == []


def test_short_replies_can_use_a_split_contextual_translation():
    assert needs_neighbor_context("ہاں")
    assert not needs_neighbor_context("کیا کل آپ بازار جائیں گے؟ یہ لمبا سوال ہے۔")
    assert choose_contextual_line("Yes.", "Will you go? Yes.") == "Yes."
    assert choose_contextual_line("Yes.", "Yes tomorrow") == "Yes."
