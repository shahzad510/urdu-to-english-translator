"""Turn Urdu speaker labels into one Latin-script label.

The model is asked to do this, and this module does it again afterwards.
Only the label is rewritten deterministically. Spoken words are left as the
model returned them, except for a few known names written as whole words.
"""

from __future__ import annotations

import re

from urdu_translator.translation.segments import contains_urdu, split_speaker

# Spellings requested for the labels that were showing up in English.
_KNOWN = {
    "نامعلوم": "Unknown",
    "احمد": "Ahmed",
    "علی": "Ali",
    "ناصر": "Naseer",
    "بلال": "Bilal",
    "جمال": "Jamal",
    "شیخ": "Sheikh",
}

_DIACRITIC = re.compile(r"[\u064b-\u065f\u0670\u0640\u200c\u200d\ufeff]")
_NAME_EDGE = r"[\u0600-\u06FF]"

# Urdu letters. A following consonant receives a short "a" so unvowelled
# names stay readable. Vowel letters do not.
_LETTER = {
    "ا": "a",
    "آ": "aa",
    "أ": "a",
    "إ": "i",
    "ب": "b",
    "پ": "p",
    "ت": "t",
    "ٹ": "t",
    "ث": "s",
    "ج": "j",
    "چ": "ch",
    "ح": "h",
    "خ": "kh",
    "د": "d",
    "ڈ": "d",
    "ذ": "z",
    "ر": "r",
    "ڑ": "r",
    "ز": "z",
    "ژ": "zh",
    "س": "s",
    "ش": "sh",
    "ص": "s",
    "ض": "z",
    "ط": "t",
    "ظ": "z",
    "ع": "a",
    "غ": "gh",
    "ف": "f",
    "ق": "q",
    "ک": "k",
    "گ": "g",
    "ل": "l",
    "م": "m",
    "ن": "n",
    "ں": "n",
    "و": "o",
    "ہ": "h",
    "ھ": "h",
    "ء": "",
    "ی": "i",
    "ے": "e",
    "ئ": "i",
    "ؤ": "o",
    "ة": "a",
    "ۃ": "a",
}
_VOWEL = set("اآأإویےئؤو")
_CONSONANT = set(_LETTER) - _VOWEL - {"ء"}


def latin_name(label: str) -> str:
    """Return the Latin form of a speaker label. English labels stay as written."""
    cleaned = " ".join(label.split())
    if cleaned in _KNOWN:
        return _KNOWN[cleaned]
    if not contains_urdu(cleaned):
        return cleaned
    words = [_latin_word(word) for word in cleaned.split(" ")]
    return " ".join(word for word in words if word)


def normalize_passthrough(line: str) -> str:
    """Rewrite a copied line when its only Urdu is the speaker label."""
    parsed = split_speaker(line)
    if parsed is None:
        return line
    indent, label, body = parsed
    if not contains_urdu(label) or contains_urdu(body):
        return line
    return _join(indent, latin_name(label), body.strip())


def normalize_translated_line(source: str, translated: str) -> str:
    """Keep one Latin label and the translated utterance."""
    parsed = split_speaker(source)
    if parsed is None:
        return _names_in_speech(translated)
    indent, label, _body = parsed
    spoken = _without_leading_labels(translated, label)
    spoken = _names_in_speech(spoken)
    if not contains_urdu(label):
        return _join(indent, label.strip(), spoken)
    return _join(indent, latin_name(label), spoken)


def _latin_word(word: str) -> str:
    if word in _KNOWN:
        return _KNOWN[word]
    if not contains_urdu(word):
        return word
    letters = _DIACRITIC.sub("", word)
    pieces: list[str] = []
    characters = list(letters)
    for index, character in enumerate(characters):
        mapped = _LETTER.get(character)
        if mapped is None:
            if character.isascii():
                pieces.append(character)
            continue
        pieces.append(mapped)
        nxt = characters[index + 1] if index + 1 < len(characters) else ""
        if character in _CONSONANT and nxt in _CONSONANT:
            pieces.append("a")
    text = "".join(pieces).strip()
    if not text:
        return ""
    return text[:1].upper() + text[1:]


def _without_leading_labels(translated: str, source_label: str) -> str:
    """Drop repeated Urdu or Latin labels the model put in front of the utterance."""
    labels = [source_label.strip()]
    if contains_urdu(source_label):
        labels.append(latin_name(source_label))
    text = translated.strip()
    changed = True
    while changed and text:
        changed = False
        for label in labels:
            if not label:
                continue
            pattern = re.compile(
                rf"^{re.escape(label)}\s*[:：]\s*۔?\s*",
                re.IGNORECASE,
            )
            updated = pattern.sub("", text, count=1)
            if updated != text:
                text = updated.lstrip()
                changed = True
                break
        if changed or len(labels) < 2:
            continue
        urdu_label, latin_label = labels[0], labels[1]
        paired = re.compile(
            rf"^{re.escape(urdu_label)}\s+{re.escape(latin_label)}\s*[:：]\s*۔?\s*",
            re.IGNORECASE,
        )
        updated = paired.sub("", text, count=1)
        if updated != text:
            text = updated.lstrip()
            changed = True
    return text


def _names_in_speech(text: str) -> str:
    """Replace known names that stand alone inside the utterance."""
    updated = text
    for source, target in sorted(_KNOWN.items(), key=lambda item: len(item[0]), reverse=True):
        pattern = re.compile(rf"(?<!{_NAME_EDGE}){re.escape(source)}(?!{_NAME_EDGE})")
        updated = pattern.sub(target, updated)
    return updated.strip()


def _join(indent: str, label: str, spoken: str) -> str:
    if not spoken:
        return f"{indent}{label}:"
    return f"{indent}{label}: {spoken}"
