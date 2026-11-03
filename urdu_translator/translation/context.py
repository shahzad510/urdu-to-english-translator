"""Neighboring-line context for short conversational replies.

The previous Urdu line is used only as model input. It is not copied into
the English line. If the combined translation cannot be split into the
previous sentence and the current one, the current sentence's own
translation is kept.
"""

from __future__ import annotations

import re

_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+")


def needs_neighbor_context(text: str) -> bool:
    """Short replies are the lines where the previous turn can change the wording."""
    words = [word for word in text.split() if word]
    return 0 < len(words) <= 8


def choose_contextual_line(solo: str, combined: str) -> str:
    """Use the last sentence of a two-sentence translation when the split is clear."""
    parts = [part.strip() for part in _SENTENCE_BREAK.split(combined.strip()) if part.strip()]
    if len(parts) >= 2 and parts[-1]:
        return parts[-1]
    return solo.strip()
