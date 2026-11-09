"""Windows path, model, and offline-server behaviour, exercised with doubles.

These tests run on Ubuntu. They do not start a Windows process and they do
not prove that a Windows installer has been built.
"""

import json
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from urdu_translator.errors import TranslationFailedError
from urdu_translator.gui.main_window import MainWindow
from urdu_translator.model_setup import (
    EXPECTED_GGUF,
    READY_STATUS,
    configured_model_status,
    copy_model_file,
    load_saved_model_path,
    save_model_path,
    unavailable_model_message,
    validate_model_file,
)
from urdu_translator.paths import (
    bundled_llama_server,
    config_dir,
    database_path,
    log_path,
    recommended_models_dir,
    temp_dir,
    user_data_dir,
    window_settings_path,
)
from urdu_translator.translation.backends.gemma import resolve_model_path, resolve_server_binary
from urdu_translator.translation.backends.llama_server import (
    LlamaServer,
    ServerSettings,
    reset_for_tests,
    server_command,
    stop_owned_server,
)
from urdu_translator.translation.loader import EngineStatus, read_package


def _gguf(path: Path, payload: bytes = b"GGUF-test") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _package(folder: Path, **extra: object):
    folder.mkdir(parents=True, exist_ok=True)
    data = {"name": "Gemma 4 E4B", "backend": "gemma", "default": True}
    data.update(extra)
    (folder / "engine.json").write_text(json.dumps(data), encoding="utf-8")
    return read_package(folder / "engine.json")


def test_windows_user_data_uses_localappdata(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    monkeypatch.delenv("URDU_TRANSLATOR_DATA", raising=False)
    monkeypatch.delenv("URDU_TRANSLATOR_DATABASE", raising=False)
    root = tmp_path / "Local" / "UrduTranslator"
    assert user_data_dir() == root
    assert database_path() == root / "History" / "history.db"
    assert log_path() == root / "Logs" / "application.log"
    assert window_settings_path() == root / "Configuration" / "window.ini"
    assert config_dir() == root / "Configuration"
    assert recommended_models_dir() == root / "Models"
    assert temp_dir() == root / "Temp"
    assert "Program Files" not in str(database_path())


def test_linux_history_stays_beside_the_existing_data_folder(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("URDU_TRANSLATOR_DATA", str(tmp_path))
    monkeypatch.delenv("URDU_TRANSLATOR_DATABASE", raising=False)
    assert database_path() == tmp_path / "history.db"
    assert log_path() == tmp_path / "application.log"
    assert window_settings_path() == tmp_path / "window.ini"


def test_a_missing_model_explains_how_to_recover(tmp_path: Path):
    missing = tmp_path / "E" / EXPECTED_GGUF
    state, message = configured_model_status(missing)
    assert state == "unavailable"
    assert EXPECTED_GGUF in message
    assert "does not download" in message
    assert "Reconnect the drive" in unavailable_model_message(missing)


def test_model_file_checks_do_not_use_a_fixed_size(tmp_path: Path):
    empty = _gguf(tmp_path / "empty.gguf", b"")
    assert "empty" in (validate_model_file(empty) or "")
    wrong = tmp_path / "notes.txt"
    wrong.write_text("hello", encoding="utf-8")
    assert ".gguf" in (validate_model_file(wrong) or "")
    other = _gguf(tmp_path / "model.gguf", b"NOPE")
    assert "not a GGUF" in (validate_model_file(other) or "")
    small = _gguf(tmp_path / EXPECTED_GGUF, b"GGUF" + b"abc")
    large = _gguf(tmp_path / "other.gguf", b"GGUF" + b"x" * 50)
    assert validate_model_file(small) is None
    assert validate_model_file(large) is None


def test_model_path_is_saved_and_reused(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("URDU_TRANSLATOR_DATA", str(tmp_path / "data"))
    chosen = _gguf(tmp_path / "usb" / EXPECTED_GGUF)
    save_model_path(chosen)
    assert load_saved_model_path() == chosen
    package = _package(
        tmp_path / "pkg",
        model_path=str(tmp_path / "somewhere-else.gguf"),
        server_bin=str(tmp_path / "llama-server"),
    )
    assert resolve_model_path(package) == chosen


def test_engine_json_still_supplies_the_linux_paths_when_nothing_is_saved(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("URDU_TRANSLATOR_DATA", str(tmp_path / "data"))
    model = tmp_path / "drive" / EXPECTED_GGUF
    binary = tmp_path / "llama-server"
    package = _package(tmp_path / "pkg", model_path=str(model), server_bin=str(binary))
    assert resolve_model_path(package) == model
    assert resolve_server_binary(package) == binary


def test_windows_bundle_is_used_when_engine_json_has_no_server_path(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr("urdu_translator.paths.install_root", lambda: tmp_path)
    binary = tmp_path / "runtime" / "llama-server.exe"
    binary.parent.mkdir()
    binary.write_bytes(b"MZ")
    assert bundled_llama_server() == binary
    package = _package(tmp_path / "pkg")
    assert resolve_server_binary(package) == binary


def test_copy_keeps_the_usb_file_and_checks_the_size(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("URDU_TRANSLATOR_DATA", str(tmp_path / "data"))
    source = _gguf(tmp_path / "usb" / EXPECTED_GGUF, b"GGUF" + b"weights")
    original = source.read_bytes()
    seen: list[tuple[int, int]] = []
    copied = copy_model_file(source, progress=lambda done, total: seen.append((done, total)))
    assert copied == recommended_models_dir() / EXPECTED_GGUF
    assert copied.read_bytes() == original
    assert source.read_bytes() == original
    assert copied.stat().st_size == source.stat().st_size
    assert seen[-1] == (len(original), len(original))
    save_model_path(copied)
    assert configured_model_status(load_saved_model_path()) == ("ready", READY_STATUS)


def test_a_removed_usb_model_stays_unavailable(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("URDU_TRANSLATOR_DATA", str(tmp_path / "data"))
    removed = tmp_path / "E" / EXPECTED_GGUF
    save_model_path(removed)
    state, message = configured_model_status(load_saved_model_path())
    assert state == "unavailable"
    assert "Reconnect the drive" in message
    assert "online" in message


def test_server_command_binds_only_to_loopback(tmp_path: Path):
    binary = tmp_path / "llama-server"
    model = _gguf(tmp_path / EXPECTED_GGUF)
    binary.write_text("binary", encoding="utf-8")
    command = server_command(ServerSettings(binary=binary, model=model))
    assert command[command.index("--host") + 1] == "127.0.0.1"
    with pytest.raises(TranslationFailedError, match="127.0.0.1"):
        server_command(ServerSettings(binary=binary, model=model, host="0.0.0.0"))


def test_a_server_that_cannot_start_is_reported(tmp_path: Path):
    binary = tmp_path / "llama-server.exe"
    model = _gguf(tmp_path / EXPECTED_GGUF)
    binary.write_bytes(b"MZ")

    def popen(_command, **_kwargs):
        raise OSError("The specified module could not be found.")

    server = LlamaServer(
        ServerSettings(binary=binary, model=model, health_timeout=0.1, stop_timeout=0.01),
        popen=popen,
        port_open=lambda: False,
    )
    with pytest.raises(TranslationFailedError, match="llama-server") as caught:
        server.ensure_started()
    assert "does not download" in str(caught.value)


def test_an_unknown_listener_is_left_running(tmp_path: Path):
    binary = tmp_path / "llama-server"
    model = _gguf(tmp_path / EXPECTED_GGUF)
    binary.write_text("binary", encoding="utf-8")
    starts: list[list[str]] = []
    server = LlamaServer(
        ServerSettings(binary=binary, model=model),
        popen=lambda command, **_kwargs: starts.append(command),
        port_open=lambda: True,
        listener_argv=lambda: None,
    )
    with pytest.raises(TranslationFailedError, match="left running"):
        server.ensure_started()
    assert starts == []


def test_clean_shutdown_with_no_owned_server():
    reset_for_tests()
    stop_owned_server()
    reset_for_tests()


def test_offline_helpers_do_not_name_a_download_url():
    root = Path(__file__).resolve().parents[1]
    for relative in (
        "urdu_translator/model_setup.py",
        "urdu_translator/gui/model_setup_dialog.py",
        "packaging/windows/build_windows.ps1",
        "packaging/windows/installer.iss",
        "packaging/windows/UrduTranslator.spec",
    ):
        text = (root / relative).read_text(encoding="utf-8").lower()
        assert "http://" not in text
        assert "https://" not in text
    spec = (root / "packaging/windows/UrduTranslator.spec").read_text(encoding="utf-8")
    assert "Refusing to bundle a GGUF model" in spec
    installer = (root / "packaging/windows/installer.iss").read_text(encoding="utf-8")
    assert "UrduTranslator-Setup-1.0.0-x64" in installer
    assert "LOCALAPPDATA" in installer
    assert ".gguf" in installer.lower()


@pytest.fixture
def qapp():
    application = QApplication.instance()
    if application is None:
        application = QApplication([])
    return application


def test_missing_model_opens_setup_and_does_not_claim_it_is_ready(qapp, tmp_path: Path, monkeypatch):
    window = MainWindow(models_directory=tmp_path / "models", history_database=tmp_path / "history.db")
    opened: list[str] = []

    class FakeDialog:
        def __init__(self, parent=None) -> None:
            self.parent = parent

        def exec(self) -> int:
            opened.append("opened")
            return 0

    monkeypatch.setattr("urdu_translator.gui.model_setup_dialog.ModelSetupDialog", FakeDialog)
    try:
        qapp.processEvents()
        window.offer_model_setup()
        assert opened == ["opened"]
        assert window.statusBar().currentMessage() != READY_STATUS
    finally:
        window.close()


def test_the_setup_dialog_names_the_model_file(qapp, tmp_path: Path):
    from PySide6.QtWidgets import QLabel

    from urdu_translator.gui.model_setup_dialog import ModelSetupDialog

    window = MainWindow(models_directory=tmp_path / "models", history_database=tmp_path / "history.db")
    try:
        dialog = ModelSetupDialog(window)
        qapp.processEvents()
        text = " ".join(label.text() for label in dialog.findChildren(QLabel))
        assert dialog.windowTitle() == "Gemma AI Model Setup"
        assert "completely offline" in text
        assert EXPECTED_GGUF in text
        assert dialog.browse_button.text() == "Browse for Model"
        assert dialog.verify_button.text() == "Verify Model"
        dialog.close()
    finally:
        window.close()


def test_a_ready_model_is_reused_without_the_dialog(qapp, tmp_path: Path, monkeypatch):
    window = MainWindow(models_directory=tmp_path / "models", history_database=tmp_path / "history.db")
    monkeypatch.setattr(
        "urdu_translator.gui.main_window.inspect_engine",
        lambda _path: EngineStatus("ready", "Gemma 4 E4B", "Ready."),
    )
    try:
        window.offer_model_setup()
        assert window.statusBar().currentMessage() == READY_STATUS
    finally:
        window.close()
