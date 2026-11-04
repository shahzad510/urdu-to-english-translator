"""The document service keeps structure and calls the engine only for Urdu."""

from pathlib import Path

import pytest

from urdu_translator.errors import TranslationFailedError
from urdu_translator.translation.engine import TranslationEngine
from urdu_translator.translation.package import ModelPackage
from urdu_translator.translation.service import translate_document


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


class EchoEngine(TranslationEngine):
    def translate_batch(self, texts: list[str]) -> list[str]:
        return [f"[{text}]" for text in texts]


class BrokenEngine(TranslationEngine):
    def translate_batch(self, texts: list[str]) -> list[str]:
        raise RuntimeError("weights could not be read")


def test_translation_preserves_report_structure():
    source = "\n".join(
        [
            "ROC/ Area:",
            "A-5/ Shahrag",
            "",
            "جمال :۔یہ پہلا جملہ ہے۔",
            "شیخ:۔ یہ دوسرا جملہ ہے۔",
            "نامعلوم:۔ N/H",
            "Analysis: ۔ یہ تجزیہ ہے۔",
            "یہ سادہ جملہ ہے۔",
        ]
    )
    result = translate_document(source, lambda: EchoEngine(_package()))
    assert result.engine_name == "Echo"
    assert result.translated_segment_count == 4
    assert result.text == "\n".join(
        [
            "ROC/ Area:",
            "A-5/ Shahrag",
            "",
            "Jamal: [یہ پہلا جملہ ہے۔]",
            "Sheikh: [یہ دوسرا جملہ ہے۔]",
            "Unknown: N/H",
            "Analysis: [یہ تجزیہ ہے۔]",
            "[یہ سادہ جملہ ہے۔]",
        ]
    )


def test_english_only_text_does_not_load_a_model():
    def fail_if_called():
        raise AssertionError("A model should not be loaded when there is no Urdu.")

    result = translate_document("Freq:\n462.225 MHz\n", fail_if_called)
    assert result.translated_segment_count == 0
    assert result.text == "Freq:\n462.225 MHz\n"
    assert result.engine_name == ""


def test_engine_failure_is_reported_without_partial_text():
    with pytest.raises(TranslationFailedError, match="weights could not be read"):
        translate_document("سلام", lambda: BrokenEngine(_package()))


def test_a_short_engine_result_is_rejected():
    class ShortEngine(TranslationEngine):
        def translate_batch(self, texts: list[str]) -> list[str]:
            return []

    with pytest.raises(TranslationFailedError, match="unexpected result"):
        translate_document("سلام\nدنیا", lambda: ShortEngine(_package()))
