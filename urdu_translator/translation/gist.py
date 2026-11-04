"""Contextual summary of a finished English translation.

The summary is a second output. It is written only after the translation has
been assembled, and it never replaces that translation. The default summary is
brief. A long text is reduced in parts and then combined into one summary.
Those parts are not separate gists.
"""

from __future__ import annotations

import inspect
import re
from collections.abc import Callable

from urdu_translator.errors import TranslationCancelled, TranslationFailedError

DEFAULT_SUMMARY_CHARS = 6000
MAX_SUMMARY_DEPTH = 6
DEFAULT_LEVEL = "brief"
SUMMARY_LEVELS = ("brief", "detailed", "expanded")

Completer = Callable[..., str]
ProgressCallback = Callable[[str], None]
StopCallback = Callable[[], bool]

_LENGTH = {
    "brief": (
        "Write a maximum of 2 or 3 concise sentences, about 35 to 55 words. "
    ),
    "detailed": (
        "Write a more detailed summary. Aim for about 70 to 100 words. "
        "That length is a target, not a rigid limit. "
    ),
    "expanded": (
        "Write an expanded summary. Aim for about 120 to 180 words. "
        "That length is a target, not a rigid limit. "
    ),
}

_SHARED = (
    "You write a contextual summary of a translated conversation or document. "
    "The text you receive is already in English. "
    "Cover the entire text, not only the last section. "
    "Summarise the overall communication, the main parties, the key activity, and the important context. "
    "Include an important location or instruction when the text makes it relevant. "
    "Use professional, neutral English. "
    "Do not repeat the text sentence by sentence. "
    "Do not add an introductory phrase, a title, or a label. "
    "Do not elaborate on every detail. Do not repeat information. "
    "Do not add unsupported assumptions, speculation, or invented facts. "
    "Where the text is uncertain, keep that uncertainty. "
    "Never convert an allegation or a reported claim into an established fact. "
    "This is a contextual summary, not an assessment. "
    "Do not add threat ratings, intentions, predictions, recommendations, or conclusions "
    "that the text does not explicitly support. "
    "Return only the summary."
)

FINAL_SYSTEM = _LENGTH["brief"] + _SHARED

PARTIAL_SYSTEM = (
    "You summarise one part of a longer translated conversation or document. "
    "A later step will combine these part summaries into one contextual summary. "
    "Do not write a separate final summary of the whole document. "
    "Include the people, locations, dates, quantities, events, communications, "
    "instructions, and developments stated in this part. "
    "Keep alleged, reported, or uncertain claims in that form. "
    "Do not add facts, intentions, predictions, recommendations, threat ratings, "
    "or conclusions that this part does not state. "
    "Return only the part summary."
)


def normalize_level(level: str | None) -> str:
    """Return a known summary level. Anything else stays at the brief default."""
    key = (level or DEFAULT_LEVEL).strip().lower()
    if key not in SUMMARY_LEVELS:
        return DEFAULT_LEVEL
    return key


def next_summary_level(level: str) -> str | None:
    """The next longer summary, or None once Expanded has been reached."""
    key = normalize_level(level)
    if key == "brief":
        return "detailed"
    if key == "detailed":
        return "expanded"
    return None


def level_label(level: str) -> str:
    """The label shown beside the gist."""
    return {"brief": "Brief", "detailed": "Detailed", "expanded": "Expanded"}[normalize_level(level)]


def system_prompt(level: str) -> str:
    """Instructions for one summary length. The source text is unchanged."""
    chosen = normalize_level(level)
    return _LENGTH[chosen] + _SHARED


def count_words(text: str) -> int:
    return len(re.findall(r"\b[\w']+\b", text))


def count_sentences(text: str) -> int:
    return len([part for part in re.split(r"[.!?]+", text.strip()) if part.strip()])


def brief_summary_is_too_long(text: str) -> bool:
    """A brief gist should stay near 2–3 sentences and about 35–55 words.

    The check is only a guard for a very long reply. A slightly shorter or
    slightly longer answer is left as the model wrote it.
    """
    return count_sentences(text) > 3 or count_words(text) > 70


def summary_char_budget(context_length: int, max_new_tokens: int) -> int:
    """How much source text one summary request should carry.

    The reply and the instructions stay inside the model's context. The
    estimate is conservative so a long document is split instead of overflowing.
    """
    reserve = max(int(max_new_tokens), 1) + 900
    room = int(context_length) - reserve
    if room < 400:
        return 1200
    return max(1200, min(room * 3, DEFAULT_SUMMARY_CHARS))


def summarize_english(
    english: str,
    complete: Completer,
    *,
    progress: ProgressCallback | None = None,
    should_stop: StopCallback | None = None,
    max_chars: int = DEFAULT_SUMMARY_CHARS,
    level: str = DEFAULT_LEVEL,
) -> str:
    """Return one contextual summary of ``english``.

    ``level`` selects Brief, Detailed, or Expanded. Each level is written from
    the full English text. ``complete`` is the translation model's existing
    chat function. This does not start a server of its own.
    """
    text = english.strip()
    if not text:
        raise TranslationFailedError(
            "There is no English text to summarise. The English translation was kept."
        )
    _stop_if_requested(should_stop)
    return _reduce(
        text,
        complete,
        progress,
        should_stop,
        max(int(max_chars), 1),
        depth=0,
        level=normalize_level(level),
    )


def split_for_summary(text: str, max_chars: int) -> list[str]:
    """Split on paragraph boundaries, then lines, without empty pieces."""
    limit = max(int(max_chars), 1)
    cleaned = text.strip()
    if len(cleaned) <= limit:
        return [cleaned]
    paragraphs = [part.strip() for part in cleaned.split("\n\n") if part.strip()]
    if not paragraphs:
        return [cleaned[:limit]]
    return _pack(paragraphs, limit, "\n\n")


def _reduce(
    text: str,
    complete: Completer,
    progress: ProgressCallback | None,
    should_stop: StopCallback | None,
    max_chars: int,
    depth: int,
    level: str,
) -> str:
    sections = split_for_summary(text, max_chars)
    if len(sections) == 1 or depth >= MAX_SUMMARY_DEPTH:
        source = sections[0] if len(sections) == 1 else _bounded(text, max_chars)
        if depth:
            _report(progress, "Combining the section summaries…")
        else:
            _report(progress, "Writing the contextual summary…")
        return _final_summary(complete, source, should_stop, combining=depth > 0, level=level)
    partials: list[str] = []
    total = len(sections)
    for number, section in enumerate(sections, start=1):
        _stop_if_requested(should_stop)
        _report(progress, f"Summarising part {number} of {total}…")
        partials.append(_part_summary(complete, section, should_stop))
    combined = "\n\n".join(
        f"Part {number}:\n{part}" for number, part in enumerate(partials, start=1)
    )
    return _reduce(combined, complete, progress, should_stop, max_chars, depth + 1, level)


def _final_summary(
    complete: Completer,
    text: str,
    should_stop: StopCallback | None,
    *,
    combining: bool,
    level: str,
) -> str:
    length = _LENGTH[level].strip()
    if combining:
        user = (
            "The notes below are partial summaries of one translated conversation "
            "or document, in order. They stand in for the entire text. "
            "Write one contextual summary of the whole. Cover every part, not only the last section. "
            "Do not repeat the notes part by part.\n\n"
            f"{length}\n\n"
            + text
        )
    else:
        user = (
            "Write one contextual summary of the entire text below. "
            "Cover the whole conversation or document, not only the last section.\n\n"
            f"{length}\n\n"
            + text
        )
    draft = _invoke(complete, system_prompt(level), user, should_stop)
    if level != "brief" or not brief_summary_is_too_long(draft):
        return draft
    shorter = (
        user
        + "\n\nThe draft below is too long. Replace it with one brief summary of the "
        "entire text, in at most 3 sentences and about 35 to 55 words. "
        "Do not add facts that are not in the text.\n\n"
        + draft
    )
    return _invoke(complete, system_prompt("brief"), shorter, should_stop)


def _part_summary(
    complete: Completer,
    text: str,
    should_stop: StopCallback | None,
) -> str:
    user = "Summarise only this part. It will be combined with the other parts later.\n\n" + text
    return _invoke(complete, PARTIAL_SYSTEM, user, should_stop)


def _pack(pieces: list[str], limit: int, separator: str) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for piece in pieces:
        for fragment in _fragments(piece, limit):
            extra = len(fragment) if not current else len(separator) + len(fragment)
            if current and size + extra > limit:
                chunks.append(separator.join(current))
                current = [fragment]
                size = len(fragment)
            else:
                current.append(fragment)
                size += extra
    if current:
        chunks.append(separator.join(current))
    return [chunk for chunk in chunks if chunk.strip()]


def _fragments(piece: str, limit: int) -> list[str]:
    """Break one oversized block into pieces that can be packed."""
    if len(piece) <= limit:
        return [piece]
    lines = [line for line in piece.split("\n") if line.strip()]
    if len(lines) > 1:
        fragments: list[str] = []
        for line in lines:
            fragments.extend(_fragments(line, limit))
        return fragments
    return [
        piece[index : index + limit]
        for index in range(0, len(piece), limit)
        if piece[index : index + limit].strip()
    ]


def _bounded(text: str, max_chars: int) -> str:
    """Keep a last-resort combination inside one request."""
    cleaned = text.strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[:max_chars].rstrip()


def _invoke(
    complete: Completer,
    system: str,
    user: str,
    should_stop: StopCallback | None,
) -> str:
    _stop_if_requested(should_stop)
    parameters = inspect.signature(complete).parameters
    accepts_keywords = any(
        item.kind == inspect.Parameter.VAR_KEYWORD for item in parameters.values()
    )
    if accepts_keywords or "should_stop" in parameters:
        raw = complete(system, user, should_stop=should_stop)
    else:
        raw = complete(system, user)
    if not isinstance(raw, str):
        raise TranslationFailedError(
            "The model did not return a contextual summary. The English translation was kept."
        )
    cleaned = _strip_fence(raw).strip()
    if not cleaned:
        raise TranslationFailedError(
            "The model returned an empty contextual summary. The English translation was kept."
        )
    return cleaned


def _strip_fence(text: str) -> str:
    cleaned = text.strip()
    if not cleaned.startswith("```"):
        return cleaned
    rows = cleaned.splitlines()
    if rows and rows[0].startswith("```"):
        rows = rows[1:]
    if rows and rows[-1].strip() == "```":
        rows = rows[:-1]
    return "\n".join(rows).strip()


def _report(progress: ProgressCallback | None, message: str) -> None:
    if progress is not None:
        progress(message)


def _stop_if_requested(should_stop: StopCallback | None) -> None:
    if should_stop is not None and should_stop():
        raise TranslationCancelled("The contextual summary was cancelled.")
