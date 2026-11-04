"""English output uses one Latin-script speaker label."""

from pathlib import Path

from urdu_translator.translation.engine import TranslationEngine
from urdu_translator.translation.package import ModelPackage
from urdu_translator.translation.service import translate_document
from urdu_translator.translation.speakers import latin_name, normalize_translated_line


def _package() -> ModelPackage:
    return ModelPackage(
        name="Fake",
        backend="fake",
        directory=Path("."),
        source_language="ur",
        target_language="en",
        is_default=True,
        options={},
    )


class _ChunkEngine(TranslationEngine):
    """Return a deliberately messy model line for each source line."""

    def __init__(self) -> None:
        super().__init__(_package())
        self.calls: list[tuple[list[str], list[str]]] = []
        self.max_chunk_chars = 8
        self.overlap_lines = 1

    def translate_batch(self, texts: list[str]) -> list[str]:
        raise AssertionError("Grouped translation should not call translate_batch.")

    def translate_chunk(self, lines: list[str], context: list[str]) -> list[str]:
        self.calls.append((list(lines), list(context)))
        return [_messy(line) for line in lines]


def _messy(line: str) -> str:
    if line.startswith("نامعلوم"):
        return "نامعلوم: Unknown: Hello"
    if line.startswith("احمد"):
        return "احمد: Ahmed: Yes, I saw علی"
    if line.startswith("علی"):
        return "OK"
    if line.startswith("John"):
        return "John: Hi"
    if line.startswith("Analysis"):
        return "Analysis: Analysis: The point stands"
    if line.startswith("ناصر"):
        return "ناصر Naseer: Tomorrow احمد will come"
    if line.startswith("بلال"):
        return "بلال: Bilal: At the market"
    return "Translated"


def test_known_speaker_names_have_stable_latin_spellings():
    assert latin_name("نامعلوم") == "Unknown"
    assert latin_name("احمد") == "Ahmed"
    assert latin_name("علی") == "Ali"
    assert latin_name("ناصر") == "Naseer"
    assert latin_name("حسن") == "Hasan"
    assert latin_name("Analysis") == "Analysis"


def test_a_name_inside_a_longer_word_is_left_alone():
    assert normalize_translated_line("احمد: سلام", "The احمدی file is ready") == (
        "Ahmed: The احمدی file is ready"
    )


def test_english_output_normalizes_labels_across_chunks():
    source = "\n".join(
        [
            "نامعلوم: سلام",
            "احمد: جی علی",
            "علی: ٹھیک",
            "",
            "John: سلام",
            "Analysis: یہ نکتہ ہے۔",
            "",
            "نامعلوم:۔ N/H",
            "",
            "ناصر: کل",
            "بلال: بازار",
        ]
    )
    engine = _ChunkEngine()
    result = translate_document(source, lambda: engine)

    assert result.source_text == source
    assert result.text == "\n".join(
        [
            "Unknown: Hello",
            "Ahmed: Yes, I saw Ali",
            "Ali: OK",
            "",
            "John: Hi",
            "Analysis: The point stands",
            "",
            "Unknown: N/H",
            "",
            "Naseer: Tomorrow Ahmed will come",
            "Bilal: At the market",
        ]
    )
    sent = [line for call in engine.calls for line in call[0]]
    assert "نامعلوم:۔ N/H" not in sent
    assert any(context for _lines, context in engine.calls)
    assert len(engine.calls) > 1
    assert engine.calls[0][0][0].startswith("نامعلوم")
    assert "احمد" not in result.text
    assert "نامعلوم" not in result.text
    assert "ناصر" not in result.text
    assert result.text.count("Unknown:") == 2
    assert result.text.count("Ahmed:") == 1
    assert "John: John:" not in result.text
    assert "Analysis: Analysis:" not in result.text
