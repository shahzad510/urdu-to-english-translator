"""Gemma is the only active engine, and a missing file does not switch models."""

import json
from pathlib import Path

import pytest

from urdu_translator.errors import TranslationFailedError
from urdu_translator.translation.backends.gemma import (
    GemmaEngine,
    cpu_only_layers,
    local_install_report,
    split_translation,
)
from urdu_translator.translation.chunks import plan_chunks
from urdu_translator.translation.engine import TranslationEngine
from urdu_translator.translation.loader import inspect_engine, load_engine, read_package
from urdu_translator.translation.package import ModelPackage
from urdu_translator.translation.registry import register_backend, unregister_backend
from urdu_translator.translation.service import translate_document
from urdu_translator.translation.terminology import terminology_from_package

ROOT = Path(__file__).resolve().parents[1]


class ChunkEngine(TranslationEngine):
    def __init__(self, replies: list[list[str]], *, max_chunk_chars: int = 12) -> None:
        super().__init__(
            ModelPackage(
                name="Chunk",
                backend="chunk",
                directory=Path("."),
                source_language="ur",
                target_language="en",
                is_default=True,
                options={},
            )
        )
        self.replies = replies
        self.calls: list[tuple[list[str], list[str]]] = []
        self.max_chunk_chars = max_chunk_chars
        self.overlap_lines = 2

    def translate_batch(self, texts: list[str]) -> list[str]:
        raise AssertionError("Grouped translation should not call translate_batch.")

    def translate_chunk(self, lines: list[str], context: list[str]) -> list[str]:
        self.calls.append((list(lines), list(context)))
        return self.replies.pop(0)


def test_cpu_inference_stays_off_the_gpu():
    assert cpu_only_layers(0) == 0
    assert cpu_only_layers(99) == 0


def test_a_missing_gemma_file_does_not_select_another_package(tmp_path: Path):
    class EchoEngine(TranslationEngine):
        def translate_batch(self, texts: list[str]) -> list[str]:
            return list(texts)

    register_backend("echo-gemma", lambda package: EchoEngine(package))
    try:
        root = tmp_path / "models"
        (root / "gemma-4-e4b").mkdir(parents=True)
        (root / "gemma-4-e4b" / "engine.json").write_text(
            json.dumps(
                {
                    "name": "Gemma 4 E4B",
                    "backend": "gemma",
                    "default": True,
                    "context_length": 8192,
                    "n_gpu_layers": 0,
                }
            ),
            encoding="utf-8",
        )
        (root / "opus").mkdir()
        (root / "opus" / "engine.json").write_text(
            json.dumps({"name": "OPUS", "backend": "echo-gemma", "default": True}),
            encoding="utf-8",
        )
        status = inspect_engine(root)
        assert status.state == "invalid"
        assert status.model_name == "Gemma 4 E4B"
        assert "does not use another translation engine" in status.message
        assert "will use the literal" not in status.message.lower()
        with pytest.raises(TranslationFailedError, match="does not use another translation engine"):
            load_engine(root)
    finally:
        unregister_backend("echo-gemma")


def test_project_models_do_not_fall_back_to_another_engine():
    from urdu_translator.translation.backends.llama_server import owned_process_pid, reset_for_tests

    try:
        status = inspect_engine(ROOT / "models")
        assert "will use the literal" not in status.message.lower()
        model = Path(
            "/media/shzy/1c58d290-c981-4926-91d9-1032ae6d9cd7/Gemma/gemma-4-E4B_q4_0-it.gguf"
        )
        binary = Path(
            "/media/shzy/1c58d290-c981-4926-91d9-1032ae6d9cd7/Gemma/llama.cpp/build/bin/llama-server"
        )
        if model.is_file() and binary.is_file():
            assert status.state == "ready"
            assert status.model_name == "Gemma 4 E4B"
            engine = load_engine(ROOT / "models")
            assert engine.name == "Gemma 4 E4B"
            assert owned_process_pid() is None
        else:
            assert status.state == "invalid"
            assert "gemma-4-E4B_q4_0-it.gguf" in status.message
            with pytest.raises(TranslationFailedError, match="does not use another translation engine"):
                load_engine(ROOT / "models")
    finally:
        reset_for_tests()


def test_chunks_keep_speakers_english_lines_and_overlap():
    source = "احمد: سلام\nبلال: جی\n\nROC/ Area:\nNorth market"
    engine = ChunkEngine([["Hello"], ["Yes"]])
    result = translate_document(source, lambda: engine)
    assert result.text == "احمد: Hello\nبلال: Yes\n\nROC/ Area:\nNorth market"
    assert engine.calls[0] == (["احمد: سلام"], [])
    assert engine.calls[1][0] == ["بلال: جی"]
    assert engine.calls[1][1] == ["احمد: سلام"]
    assert all("ROC/ Area:" not in call[0] for call in engine.calls)


def test_an_english_line_inside_a_group_is_restored():
    source = "احمد: سلام\nN/H"
    engine = ChunkEngine([["Hi", "changed"]], max_chunk_chars=80)
    result = translate_document(source, lambda: engine)
    assert result.text == "احمد: Hi\nN/H"


def test_a_line_count_mismatch_is_an_error():
    engine = ChunkEngine([["only one"]], max_chunk_chars=80)
    with pytest.raises(TranslationFailedError, match="same number of lines"):
        translate_document("احمد: سلام\nبلال: جی", lambda: engine)


def test_prompt_includes_context_glossary_and_the_8k_default(tmp_path: Path):
    (tmp_path / "terminology.json").write_text(
        json.dumps({"terms": [{"source": "کراچی", "target": "Karachi", "kind": "place"}]}),
        encoding="utf-8",
    )
    folder = tmp_path / "gemma"
    folder.mkdir()
    (folder / "engine.json").write_text(
        json.dumps(
            {
                "name": "Gemma 4 E4B",
                "backend": "gemma",
                "default": True,
                "context_length": 8192,
                "n_gpu_layers": 32,
            }
        ),
        encoding="utf-8",
    )
    package = read_package(folder / "engine.json")
    seen: dict[str, str] = {}

    def complete(system: str, user: str) -> str:
        seen["system"] = system
        seen["user"] = user
        return "Karachi"

    from urdu_translator.translation.backends.gemma import _settings

    engine = GemmaEngine(
        package,
        terminology_from_package(folder, None),
        complete,
        **_settings(package),
    )
    assert engine.context_length == 8192
    assert engine.n_gpu_layers == 0
    assert engine.max_chunk_chars <= 1600
    assert engine.translate_chunk(["کراچی"], ["احمد: پہلے"]) == ["Karachi"]
    assert "Karachi" in seen["user"]
    assert "احمد: پہلے" in seen["user"]
    assert "Do not include them" in seen["user"]
    assert "speaker label" in seen["system"].lower()
    assert "exactly 1 lines" in seen["user"]


def test_a_code_fence_is_removed_and_a_bad_count_is_rejected():
    assert split_translation("```\nHello\n```", 1) == ["Hello"]
    with pytest.raises(TranslationFailedError, match="same number of lines"):
        split_translation("Hello\nExtra", 1)


def test_overlap_plan_keeps_indexes_in_order():
    texts = ["aaaa", "bbbb", ""]
    flags = [True, True, False]
    planned = plan_chunks(texts, flags, max_chars=4, overlap_lines=1)
    assert [chunk.indexes for chunk in planned] == [(0,), (1,), (2,)]
    assert planned[1].context_indexes == (0,)
    assert planned[1].translate is True
    assert planned[2].translate is False


def test_install_report_does_not_download_or_claim_the_weights(tmp_path: Path):
    report = local_install_report(tmp_path / "gemma-4-e4b")
    assert "Apache 2.0" in report
    assert "4.5 GB" in report
    assert "8192" in report
    assert "does not download" in report
    assert "not installed" in report
    assert "llama-server" in report
    assert "llama-cpp-python" not in report
    assert not (tmp_path / "gemma-4-e4b").exists() or not any((tmp_path / "gemma-4-e4b").glob("*.gguf"))
