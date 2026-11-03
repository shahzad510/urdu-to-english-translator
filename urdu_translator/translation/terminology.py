"""Configurable terminology for utterance text.

Speaker labels never reach this module. Names, places, and technical terms
are copied through in both modes. Ordinary expressions are not forced when
the surrounding sentence could change the wording. Existing English tokens
and numbers stay in place. Placeholders are not used, because the Marian
model rewrites them.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from pathlib import Path

from urdu_translator.errors import TranslationFailedError

_LATIN = re.compile(r"[A-Za-z]+(?:[./+\-][A-Za-z0-9]+)*")
_NUMBER = re.compile(r"\d+(?:[.,:]\d+)*")
_EDGE = set(" \t\r\n.,;:!?؟،؛۔\"'`“”()[]{}<>/\\-–—")
_KINDS = {"name", "place", "technical", "expression", "user"}
_ANCHORS = {"name", "place", "technical"}


@dataclass(frozen=True)
class Term:
    """One preferred translation."""

    source: str
    target: str
    kind: str = "expression"


class Terminology:
    """Longest-match dictionary plus copies of English tokens and numbers."""

    def __init__(self, terms: list[Term]) -> None:
        ordered = sorted(terms, key=lambda term: len(term.source), reverse=True)
        self.terms = ordered
        self._by_source = {term.source: term for term in ordered}
        pattern = "|".join(re.escape(term.source) for term in ordered)
        self._pattern = re.compile(pattern) if pattern else None

    def plan(self, text: str, mode: str = "literal") -> list[tuple[str, str]]:
        """Split ``text`` into ``("keep", value)`` and ``("translate", value)`` pieces.

        Kept pieces are allowed terminology targets, English tokens, and numbers.
        Translate pieces are the Urdu around them. Leading punctuation stays
        out of the model text; trailing punctuation stays with the Urdu.
        """
        pieces: list[tuple[str, str]] = []
        cursor = 0
        for start, end, literal in self._keep_spans(text, mode):
            if start > cursor:
                pieces.extend(_translate_pieces(text[cursor:start]))
            pieces.append(("keep", literal))
            cursor = end
        if cursor < len(text):
            pieces.extend(_translate_pieces(text[cursor:]))
        return [(kind, value) for kind, value in pieces if value]

    def _keep_spans(self, text: str, mode: str) -> list[tuple[int, int, str]]:
        spans: list[tuple[int, int, str]] = []
        if self._pattern is not None:
            for match in self._pattern.finditer(text):
                term = self._by_source.get(match.group(0))
                if term is None or not _term_applies(term, text, match.start(), match.end(), mode):
                    continue
                spans.append((match.start(), match.end(), term.target))
        covered = [(start, end) for start, end, _literal in spans]
        for pattern in (_LATIN, _NUMBER):
            for match in pattern.finditer(text):
                if _overlaps(match.span(), covered):
                    continue
                spans.append((match.start(), match.end(), match.group(0)))
                covered.append(match.span())
        spans.sort(key=lambda item: item[0])
        return spans


def terminology_from_package(directory: Path, raw_option: object) -> Terminology:
    """Load the shared dictionary and the dictionary named by one model package."""
    paths: list[Path] = []
    shared = directory.parent / "terminology.json"
    if shared.is_file():
        paths.append(shared)
    paths.extend(_dictionary_paths(directory, raw_option))
    merged: dict[str, Term] = {}
    for path in paths:
        for term in _read_dictionary(path):
            merged[term.source] = term
    return Terminology(list(merged.values()))


def _dictionary_paths(directory: Path, raw_option: object) -> list[Path]:
    root = directory.resolve()
    if raw_option is None:
        candidate = root / "terminology.json"
        return [candidate] if candidate.is_file() else []
    values = raw_option if isinstance(raw_option, list) else [raw_option]
    paths: list[Path] = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise TranslationFailedError("Each terminology entry must be a file name inside the model folder.")
        path = Path(value)
        if path.is_absolute():
            raise TranslationFailedError("The terminology file must stay inside the model folder.")
        resolved = (root / path).resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise TranslationFailedError("The terminology file must stay inside the model folder.") from exc
        if not resolved.is_file():
            raise TranslationFailedError(f"The terminology file {value} was not found in the model folder.")
        paths.append(resolved)
    return paths


def _read_dictionary(path: Path) -> list[Term]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise TranslationFailedError(f"Could not read {path.name}. {exc}") from exc
    except json.JSONDecodeError as exc:
        raise TranslationFailedError(f"{path.name} is not valid JSON. {exc}") from exc

    pairs: list[tuple[str, str, str]] = []
    if isinstance(data, dict) and isinstance(data.get("terms"), list):
        for item in data["terms"]:
            if not isinstance(item, dict):
                raise TranslationFailedError(f"Each entry in {path.name} needs a source and a target.")
            pairs.append((str(item.get("source", "")), str(item.get("target", "")), str(item.get("kind", ""))))
    elif isinstance(data, dict):
        for source, target in data.items():
            if source == "terms":
                continue
            pairs.append((str(source), str(target), ""))
    elif isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                raise TranslationFailedError(f"Each entry in {path.name} needs a source and a target.")
            pairs.append((str(item.get("source", "")), str(item.get("target", "")), str(item.get("kind", ""))))
    else:
        raise TranslationFailedError(
            f"{path.name} must be a dictionary of Urdu phrases to English phrases."
        )

    terms: list[Term] = []
    for source, target, kind in pairs:
        source = source.strip()
        target = target.strip()
        if source and target:
            terms.append(Term(source, target, _infer_kind(source, kind)))
    return terms


def _infer_kind(source: str, raw_kind: str) -> str:
    kind = raw_kind.strip().lower()
    if kind in _KINDS:
        return kind
    if " " in source.strip():
        return "expression"
    return "user"


def _term_applies(term: Term, text: str, start: int, end: int, mode: str) -> bool:
    """Names, places, and technical terms may be replaced. Other words may not."""
    if not _is_bounded(text, start, end):
        return False
    whole_utterance = text.strip() == term.source
    if term.kind in _ANCHORS:
        return True
    if mode == "contextual":
        return whole_utterance
    if term.kind == "expression" and " " in term.source.strip():
        return True
    return whole_utterance


def _is_bounded(text: str, start: int, end: int) -> bool:
    before = text[start - 1] if start > 0 else " "
    after = text[end] if end < len(text) else " "
    return not _is_word_char(before) and not _is_word_char(after)


def _is_word_char(char: str) -> bool:
    if char in _EDGE:
        return False
    return char.isalnum() or "\u0600" <= char <= "\u06ff"


def _translate_pieces(fragment: str) -> list[tuple[str, str]]:
    if not fragment:
        return []
    if not _has_urdu_letter(fragment):
        return [("keep", fragment)]
    prefix, core, suffix = _peel(fragment)
    pieces: list[tuple[str, str]] = []
    if prefix:
        pieces.append(("keep", prefix))
    if core:
        pieces.append(("translate", core))
    if suffix:
        pieces.append(("keep", suffix))
    return pieces


def _peel(text: str) -> tuple[str, str, str]:
    """Take punctuation off the front of a fragment and whitespace off the end.

    Trailing Urdu punctuation stays on the fragment. This model uses it, and
    stripping it changes the wording.
    """
    start = 0
    end = len(text)
    while start < end and text[start] in _EDGE:
        start += 1
    while end > start and text[end - 1] in " \t\r\n":
        end -= 1
    return text[:start], text[start:end], text[end:]


def _has_urdu_letter(text: str) -> bool:
    return any("\u0600" <= char <= "\u06ff" and char not in _EDGE for char in text)


def _overlaps(span: tuple[int, int], occupied: list[tuple[int, int]]) -> bool:
    start, end = span
    return any(not (end <= left or start >= right) for left, right in occupied)
