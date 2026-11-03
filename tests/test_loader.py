"""Model discovery stays on disk and does not name a model in the interface."""

import json
from pathlib import Path

from urdu_translator.translation.engine import TranslationEngine
from urdu_translator.translation.loader import inspect_engine, load_engine
from urdu_translator.translation.registry import register_backend, unregister_backend


def _write_package(folder: Path, payload: dict) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "engine.json").write_text(json.dumps(payload), encoding="utf-8")


def test_missing_model_is_a_clear_local_status(tmp_path: Path):
    status = inspect_engine(tmp_path / "models")
    assert status.state == "missing"
    assert status.short_label == "No model loaded"
    assert str(tmp_path / "models") in status.message


def test_invalid_engine_json_is_reported(tmp_path: Path):
    folder = tmp_path / "models" / "broken"
    folder.mkdir(parents=True)
    (folder / "engine.json").write_text("{", encoding="utf-8")
    status = inspect_engine(tmp_path / "models")
    assert status.state == "invalid"


def test_known_package_without_a_backend_is_unsupported(tmp_path: Path):
    _write_package(
        tmp_path / "models" / "local-model",
        {"name": "Desk model", "backend": "not-installed", "default": True},
    )
    status = inspect_engine(tmp_path / "models")
    assert status.state == "unsupported"
    assert status.model_name == "Desk model"
    assert "not-installed" in status.message


def test_literal_and_contextual_packages_are_selected_separately(tmp_path: Path):
    class EchoEngine(TranslationEngine):
        def translate_batch(self, texts: list[str]) -> list[str]:
            return list(texts)

    register_backend("echo-role", lambda package: EchoEngine(package))
    try:
        root = tmp_path / "models"
        _write_package(
            root / "literal-model",
            {"name": "Literal model", "backend": "echo-role", "role": "literal", "default": True},
        )
        _write_package(
            root / "context-model",
            {"name": "Context model", "backend": "echo-role", "role": "contextual"},
        )
        status = inspect_engine(root)
        assert status.state == "ready"
        assert status.short_label == "Literal model"
        assert "Context model" in status.message
        assert load_engine(root, role="literal").name == "Literal model"
        assert load_engine(root, role="contextual").name == "Context model"
    finally:
        unregister_backend("echo-role")


def test_several_packages_require_one_default(tmp_path: Path):
    root = tmp_path / "models"
    _write_package(root / "one", {"name": "One", "backend": "echo"})
    _write_package(root / "two", {"name": "Two", "backend": "echo"})
    status = inspect_engine(root)
    assert status.state == "invalid"
    assert "Several model packages" in status.message


def test_registered_backend_loads_the_selected_package(tmp_path: Path):
    class EchoEngine(TranslationEngine):
        def translate_batch(self, texts: list[str]) -> list[str]:
            return list(texts)

    def factory(package):
        return EchoEngine(package)

    register_backend("echo-test", factory)
    try:
        _write_package(
            tmp_path / "models" / "echo",
            {
                "name": "Echo model",
                "backend": "echo-test",
                "source_language": "ur",
                "target_language": "en",
                "vocab": "local.bin",
            },
        )
        status = inspect_engine(tmp_path / "models")
        assert status.state == "ready"
        assert status.short_label == "Echo model"

        engine = load_engine(tmp_path / "models")
        assert engine.name == "Echo model"
        assert engine.package.options == {"vocab": "local.bin"}
        assert engine.translate_batch(["سلام"]) == ["سلام"]
    finally:
        unregister_backend("echo-test")
