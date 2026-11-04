"""Split a document into lines that keep speaker labels and paragraph breaks.

Reports in this project put a speaker name, an ASCII colon, and an Urdu full
stop before the utterance, for example ``جمال :۔سلام``. English report fields
such as ``Freq:`` sit on their own lines. Those labels stay in the output.
Only the Urdu utterance is handed to the translation engine.

A line with no Urdu characters is copied unchanged, so headings, frequencies,
and markers such as ``N/H`` survive even when a model is connected later.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

_ARABIC = re.compile(
    r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]"
)
_SPEAKER = re.compile(
    r"^(?P<indent>[ \t]*)"
    r"(?P<label>[^\n:：]{1,40}?)"
    r"(?P<separator>[ \t]*[:：][ \t]*۔?[ \t]*)"
    r"(?P<body>.*)$"
)


@dataclass(frozen=True)
class Segment:
    """One source line and the part of it, if any, that needs translation."""

    original: str
    indent: str = ""
    label: str | None = None
    separator: str = ""
    body: str = ""
    needs_translation: bool = False

    def source_for_engine(self) -> str:
        """Text that should be translated, without the speaker label."""
        if self.label is not None:
            return self.body.strip()
        return self.original.strip()


def contains_urdu(text: str) -> bool:
    """Return True when ``text`` contains Arabic-script characters used by Urdu."""
    return _ARABIC.search(text) is not None


def segment_document(text: str) -> list[Segment]:
    """Split ``text`` into one segment per line, preserving blank lines."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return [_segment_line(line) for line in normalized.split("\n")]


def render_document(segments: list[Segment], translations: list[str]) -> str:
    """Rebuild the document, inserting translations in segment order.

    ``translations`` must contain one string for each segment that needs
    translation, and no others. Newlines inside a translation are flattened
    so each source line stays on its own output line.
    """
    expected = sum(segment.needs_translation for segment in segments)
    if len(translations) != expected:
        raise ValueError(
            "The translation engine returned "
            f"{len(translations)} lines for {expected} Urdu lines."
        )

    from urdu_translator.translation.speakers import normalize_passthrough, normalize_translated_line

    cursor = 0
    rendered: list[str] = []
    for segment in segments:
        if not segment.needs_translation:
            rendered.append(normalize_passthrough(segment.original))
            continue
        translated = _single_line(translations[cursor])
        cursor += 1
        rendered.append(normalize_translated_line(segment.original, translated))
    return "\n".join(rendered)


def _segment_line(line: str) -> Segment:
    if line.strip() == "" or not contains_urdu(line):
        return Segment(original=line)

    match = _SPEAKER.match(line)
    if match and _valid_label(match.group("label")):
        body = match.group("body")
        if contains_urdu(body) and body.strip():
            return Segment(
                original=line,
                indent=match.group("indent"),
                label=match.group("label"),
                separator=match.group("separator"),
                body=body,
                needs_translation=True,
            )
        return Segment(original=line)

    if not line.strip():
        return Segment(original=line)
    return Segment(original=line, body=line, needs_translation=True)


def speaker_prefix(line: str) -> str | None:
    """Return the speaker label and separator, when the line has a real label."""
    match = _SPEAKER.match(line)
    if match is None or not _valid_label(match.group("label")):
        return None
    return f"{match.group('indent')}{match.group('label')}{match.group('separator')}"


def split_speaker(line: str) -> tuple[str, str, str] | None:
    """Return indent, label, and utterance when the line has a real speaker label."""
    match = _SPEAKER.match(line)
    if match is None or not _valid_label(match.group("label")):
        return None
    return match.group("indent"), match.group("label"), match.group("body")


def _valid_label(label: str) -> bool:
    """Accept short speaker names and English field labels, not whole sentences."""
    stripped = label.strip()
    if not stripped or len(stripped) > 40:
        return False
    if "://" in stripped:
        return False
    if any(mark in stripped for mark in ("۔", "؟", "!", "?")):
        return False
    words = stripped.split()
    if contains_urdu(stripped):
        return len(words) <= 3 and len(stripped) <= 24
    return len(words) <= 4


def _single_line(text: str) -> str:
    return " ".join(text.replace("\r", "\n").split("\n")).strip()
