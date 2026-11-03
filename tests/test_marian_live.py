"""Live OPUS-MT check on a synthetic conversation.

Skipped when the local weights are not installed. The transcript is invented
and is not taken from a real report.

The application loader does not select this folder while Gemma is configured.
This test opens the OPUS-MT package directly so the unused engine can still
be checked.
"""

from pathlib import Path

import pytest

from tests.test_transcript import CONVERSATION
from urdu_translator.translation.backends.marian import load_marian_engine
from urdu_translator.translation.loader import read_package
from urdu_translator.translation.service import translate_document

ROOT = Path(__file__).resolve().parents[1]
WEIGHTS = ROOT / "models" / "opus-mt-ur-en" / "pytorch_model.bin"

pytestmark = pytest.mark.skipif(
    not WEIGHTS.is_file(),
    reason="local OPUS-MT weights are not installed",
)


def test_local_model_translates_a_conversation_without_dropping_structure():
    pytest.importorskip("torch")
    package = read_package(ROOT / "models" / "opus-mt-ur-en" / "engine.json")
    result = translate_document(CONVERSATION, lambda: load_marian_engine(package))
    lines = result.text.splitlines()

    assert result.translated_segment_count == 5
    assert lines[0].startswith("احمد: ")
    assert lines[1].startswith("بلال: ")
    assert lines[2] == ""
    assert "ROC/ Area:" in lines
    assert "North market" in lines
    assert "Peace be upon you" in lines[0]
    assert "And peace be upon you" in lines[1]
    assert "I'm fine" in lines[1]
    assert "market" in result.text.lower()
    assert "N/H" in result.text
    lowered = result.text.lower()
    assert "_dep" not in lowered
    assert "xisey" not in lowered
    assert "pa_a" not in lowered
