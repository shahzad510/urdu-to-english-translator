"""Theme entry point.

Colours live in :mod:`urdu_translator.gui.appearance`. This module remains so
older imports still resolve to that theme.
"""

from urdu_translator.gui.appearance import DEFAULT_APPEARANCE, stylesheet

STYLESHEET = stylesheet(DEFAULT_APPEARANCE)
