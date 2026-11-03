"""Group a transcript so a long document is translated with surrounding lines.

Blank lines separate paragraph groups. English-only groups are copied.
Urdu groups are sent together. A group that is too long is split, and the
previous lines stay in the prompt as overlap. They are not emitted twice.
"""

from __future__ import annotations

from dataclasses import dataclass

from urdu_translator.translation.segments import speaker_prefix


@dataclass(frozen=True)
class PlannedChunk:
    """Lines that are copied or translated together."""

    translate: bool
    indexes: tuple[int, ...]
    context_indexes: tuple[int, ...] = ()


def plan_chunks(
    texts: list[str],
    translate_flags: list[bool],
    *,
    max_chars: int,
    overlap_lines: int,
) -> list[PlannedChunk]:
    """Plan copy and translate chunks in original order."""
    if len(texts) != len(translate_flags):
        raise ValueError("Each line needs a translation flag.")
    limit = max(max_chars, 1)
    overlap = max(overlap_lines, 0)
    chunks: list[PlannedChunk] = []
    previous: tuple[int, ...] = ()
    index = 0
    total = len(texts)
    while index < total:
        if texts[index].strip() == "":
            chunks.append(PlannedChunk(False, (index,)))
            index += 1
            continue
        end = index
        while end < total and texts[end].strip() != "":
            end += 1
        group = list(range(index, end))
        if not any(translate_flags[line] for line in group):
            chunks.append(PlannedChunk(False, tuple(group)))
            index = end
            continue
        cursor = 0
        while cursor < len(group):
            chosen = [group[cursor]]
            size = len(texts[group[cursor]])
            nxt = cursor + 1
            while nxt < len(group):
                extra = len(texts[group[nxt]]) + 1
                if size + extra > limit:
                    break
                chosen.append(group[nxt])
                size += extra
                nxt += 1
            context = previous[-overlap:] if overlap else ()
            chunks.append(PlannedChunk(True, tuple(chosen), tuple(context)))
            previous = tuple(chosen)
            cursor = nxt
        index = end
    return chunks


def with_original_speaker(source: str, translated: str) -> str:
    """Keep the source speaker label when the model drops or changes it."""
    prefix = speaker_prefix(source)
    if prefix is None:
        return translated
    if translated.startswith(prefix):
        return translated
    return f"{prefix}{translated.lstrip()}"
