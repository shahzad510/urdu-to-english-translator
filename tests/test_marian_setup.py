"""Marian setup stays local and does not require weights to be present."""

import json
from pathlib import Path

import pytest

from urdu_translator.errors import TranslationFailedError
from urdu_translator.translation.backends.marian import resolve_device
from urdu_translator.translation.loader import inspect_engine, load_engine
from urdu_translator.translation.registry import registered_backends


def test_marian_backend_is_registered():
    assert "marian" in registered_backends()


def test_device_selection_without_a_gpu():
    assert resolve_device("auto", cuda_available=False) == "cpu"
    assert resolve_device("cpu", cuda_available=True) == "cpu"
    assert resolve_device("gpu", cuda_available=True) == "cuda"
    with pytest.raises(TranslationFailedError, match="no CUDA"):
        resolve_device("cuda", cuda_available=False)
    with pytest.raises(TranslationFailedError, match="Unknown device"):
        resolve_device("tpu", cuda_available=False)


def test_missing_weights_are_reported_without_loading(tmp_path: Path):
    package = tmp_path / "models" / "local-marian"
    package.mkdir(parents=True)
    (package / "engine.json").write_text(
        json.dumps(
            {
                "name": "Local Marian",
                "backend": "marian",
                "default": True,
                "device": "cpu",
            }
        ),
        encoding="utf-8",
    )
    status = inspect_engine(tmp_path / "models")
    assert status.state == "invalid"
    assert status.model_name == "Local Marian"
    assert "does not download" in status.message

    with pytest.raises(TranslationFailedError, match="does not download"):
        load_engine(tmp_path / "models")
