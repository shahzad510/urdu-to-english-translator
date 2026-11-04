"""Representative conversation transcripts keep their shape in batches."""

from urdu_translator.translation.engine import TranslationEngine
from urdu_translator.translation.package import ModelPackage
from urdu_translator.translation.service import translate_document
from pathlib import Path


CONVERSATION = "\n".join(
    [
        "احمد: السلام علیکم، آپ کیسے ہیں؟",
        "بلال: وعلیکم السلام، میں ٹھیک ہوں۔",
        "",
        "احمد: کیا کل آپ بازار جائیں گے؟",
        "بلال: ہاں، صبح نو بجے نکلنا ہے۔",
        "احمد: ٹھیک ہے، میں N/H ساتھ لاؤں گا۔",
        "",
        "ROC/ Area:",
        "North market",
    ]
)


class _Package(ModelPackage):
    pass


def _package() -> ModelPackage:
    return ModelPackage(
        name="Echo",
        backend="echo",
        directory=Path("."),
        source_language="ur",
        target_language="en",
        is_default=True,
        options={},
    )


class RecordingEngine(TranslationEngine):
    def __init__(self) -> None:
        super().__init__(_package())
        self.batches: list[list[str]] = []
        self.preferred_batch_size = 2

    def translate_batch(self, texts: list[str]) -> list[str]:
        self.batches.append(list(texts))
        return [f"[{text}]" for text in texts]


def test_conversation_keeps_labels_breaks_and_english_lines():
    engine = RecordingEngine()
    result = translate_document(CONVERSATION, lambda: engine)
    assert result.engine_name == "Echo"
    assert "ROC/ Area:" in result.text
    assert "North market" in result.text
    assert "\n\n" in result.text
    assert result.text.splitlines()[0].startswith("Ahmed: ")
    assert "[السلام علیکم، آپ کیسے ہیں؟]" in result.text
    assert "N/H" in result.text
    joined = " ".join(part for batch in engine.batches for part in batch)
    assert "ROC/ Area:" not in joined
    assert "North market" not in joined
    assert "احمد:" not in joined
    assert engine.batches[0] == [
        "السلام علیکم، آپ کیسے ہیں؟",
        "وعلیکم السلام، میں ٹھیک ہوں۔",
    ]
    assert any("N/H" in line for batch in engine.batches for line in batch)


def test_a_long_transcript_is_split_into_batches():
    lines = [f"شخص: یہ جملہ نمبر {index} ہے۔" for index in range(5)]
    engine = RecordingEngine()
    translate_document("\n".join(lines), lambda: engine)
    assert [len(batch) for batch in engine.batches] == [2, 2, 1]
