"""Terminology keeps preferred wording and existing English tokens."""

import json
from pathlib import Path

import pytest

from urdu_translator.errors import TranslationFailedError
from urdu_translator.translation.terminology import Term, Terminology, terminology_from_package


def _kept(glossary: Terminology, text: str) -> list[str]:
    return [value for kind, value in glossary.plan(text) if kind == "keep"]


def _translated(glossary: Terminology, text: str) -> list[str]:
    return [value for kind, value in glossary.plan(text) if kind == "translate"]


def test_longer_phrase_wins():
    glossary = Terminology(
        [
            Term("سلام", "hi"),
            Term("السلام علیکم", "Peace be upon you"),
        ]
    )
    kept = _kept(glossary, "احمد نے کہا السلام علیکم")
    assert "Peace be upon you" in kept
    assert "hi" not in kept
    assert all("السلام" not in part for part in _translated(glossary, "احمد نے کہا السلام علیکم"))


def test_plain_urdu_is_one_translation_piece():
    glossary = Terminology([])
    assert glossary.plan("آپ کیسے ہیں؟") == [("translate", "آپ کیسے ہیں؟")]


def test_english_tokens_and_numbers_stay_out_of_the_model_text():
    glossary = Terminology([])
    text = "براہ کرم N/H بھیجیں، تعدد 462.225 ہے"
    kept = _kept(glossary, text)
    assert "N/H" in kept
    assert "462.225" in kept
    for part in _translated(glossary, text):
        assert "N/H" not in part
        assert "462.225" not in part


def test_punctuation_around_a_term_is_kept_off_the_model_text():
    glossary = Terminology([Term("وعلیکم السلام", "And peace be upon you")])
    assert glossary.plan("وعلیکم السلام، میں ٹھیک ہوں۔") == [
        ("keep", "And peace be upon you"),
        ("keep", "، "),
        ("translate", "میں ٹھیک ہوں۔"),
    ]


def test_dictionary_file_loads_from_the_model_folder(tmp_path: Path):
    (tmp_path / "terminology.json").write_text(
        json.dumps({"terms": [{"source": "کراچی", "target": "Karachi", "kind": "place"}]}),
        encoding="utf-8",
    )
    glossary = terminology_from_package(tmp_path, None)
    assert "Karachi" in _kept(glossary, "وہ کراچی گیا")
    assert all("کراچی" not in part for part in _translated(glossary, "وہ کراچی گیا"))


def test_a_single_common_word_is_not_replaced_inside_a_sentence():
    glossary = Terminology([Term("بازار", "market", "user")])
    text = "ہم بازار جائیں گے"
    assert "market" not in _kept(glossary, text)
    assert glossary.plan(text, "contextual") == glossary.plan(text)


def test_an_expression_is_kept_only_when_it_is_the_whole_line_in_contextual_mode():
    glossary = Terminology([Term("السلام علیکم", "Peace be upon you", "expression")])
    embedded = "السلام علیکم، آپ کیسے ہیں؟"
    assert "Peace be upon you" in _kept(glossary, embedded)
    contextual = glossary.plan(embedded, "contextual")
    assert all(value != "Peace be upon you" for _kind, value in contextual)
    assert glossary.plan("السلام علیکم", "contextual") == [("keep", "Peace be upon you")]


def test_dictionary_path_cannot_leave_the_model_folder(tmp_path: Path):
    with pytest.raises(TranslationFailedError, match="inside the model folder"):
        terminology_from_package(tmp_path, "../outside.json")
