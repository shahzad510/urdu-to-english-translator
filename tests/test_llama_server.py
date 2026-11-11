"""The llama.cpp server client never starts the real binary in this file's unit tests."""

import json
import os
import subprocess
from pathlib import Path

import pytest

from urdu_translator.errors import TranslationCancelled, TranslationFailedError
from urdu_translator.translation.backends.llama_server import (
    ServerSettings,
    check_files,
    compatible_listener,
    extract_model_argument,
    is_llama_server_executable,
    parse_windows_command_line,
    port_conflict_message,
    reset_for_tests,
    server_command,
    visible_translation,
)
from urdu_translator.translation.backends.llama_server import LlamaServer


class FakeProc:
    def __init__(self, pid: int = 4321) -> None:
        self.pid = pid
        self.returncode = None
        self.signals: list[str] = []

    def poll(self):
        return self.returncode

    def terminate(self) -> None:
        self.signals.append("term")
        self.returncode = -15

    def kill(self) -> None:
        self.signals.append("kill")
        self.returncode = -9

    def wait(self, timeout: float | None = None):
        if self.returncode is None:
            raise subprocess.TimeoutExpired("llama-server", timeout or 0)
        return self.returncode


class StubbornProc(FakeProc):
    def terminate(self) -> None:
        self.signals.append("term")


class ReusedPidProc(StubbornProc):
    def wait(self, timeout: float | None = None):
        self.pid += 1
        raise subprocess.TimeoutExpired("llama-server", timeout or 0)


class FakeConn:
    def __init__(self) -> None:
        self.closed = False
        self.requested = False

    def request(self, method, path, body=None, headers=None) -> None:
        self.requested = True

    def getresponse(self):
        raise TimeoutError()

    def close(self) -> None:
        self.closed = True


def _settings(tmp_path: Path) -> ServerSettings:
    binary = tmp_path / "llama-server"
    model = tmp_path / "gemma-4-E4B_q4_0-it.gguf"
    binary.write_text("binary", encoding="utf-8")
    model.write_text("weights", encoding="utf-8")
    return ServerSettings(
        binary=binary,
        model=model,
        health_timeout=0.05,
        request_timeout=1,
        stop_timeout=0.01,
    )


def test_command_uses_the_verified_arguments_only(tmp_path: Path):
    settings = _settings(tmp_path)
    command = server_command(settings)
    assert command == [
        str(settings.binary),
        "-m",
        str(settings.model),
        "-c",
        "8192",
        "-t",
        "4",
        "--reasoning",
        "off",
        "--host",
        "127.0.0.1",
        "--port",
        "8080",
    ]
    assert "--hf-repo" not in command
    assert "--model-url" not in command
    assert "--reasoning-budget" not in command
    assert "--reasoning-format" not in command


def test_a_missing_model_names_the_gguf(tmp_path: Path):
    model = tmp_path / "gemma-4-E4B_q4_0-it.gguf"
    binary = tmp_path / "llama-server"
    binary.write_text("binary", encoding="utf-8")
    with pytest.raises(TranslationFailedError, match="gemma-4-E4B_q4_0-it.gguf") as caught:
        check_files(model, binary)
    assert "external drive or model file is unavailable" in str(caught.value)
    assert "does not use another translation engine" in str(caught.value)


def test_a_missing_server_binary_is_reported(tmp_path: Path):
    model = tmp_path / "gemma-4-E4B_q4_0-it.gguf"
    model.write_text("weights", encoding="utf-8")
    with pytest.raises(TranslationFailedError, match="llama-server") as caught:
        check_files(model, tmp_path / "missing-llama-server")
    assert "does not use another translation engine" in str(caught.value)


def test_health_success_starts_one_process_and_reuses_it(tmp_path: Path):
    settings = _settings(tmp_path)
    proc = FakeProc()
    starts: list[list[str]] = []

    def popen(command, **_kwargs):
        starts.append(command)
        return proc

    def exchange(method, path, _payload, _timeout, _should_stop):
        assert method == "GET"
        assert path == "/health"
        return 200, b'{"status":"ok"}'

    server = LlamaServer(
        settings,
        popen=popen,
        exchange=exchange,
        port_open=lambda: False,
        sleeper=lambda _seconds: None,
    )
    server.ensure_started()
    server.ensure_started()
    assert len(starts) == 1
    assert server.owned_pid() == proc.pid
    assert proc.signals == []


def test_health_timeout_stops_only_the_process_this_app_started(tmp_path: Path):
    settings = _settings(tmp_path)
    proc = FakeProc()

    def exchange(_method, _path, _payload, _timeout, _should_stop):
        return 503, b"loading"

    server = LlamaServer(
        settings,
        popen=lambda _command, **_kwargs: proc,
        exchange=exchange,
        port_open=lambda: False,
        sleeper=lambda _seconds: None,
    )
    with pytest.raises(TranslationFailedError, match="did not become ready"):
        server.ensure_started()
    assert proc.signals == ["term"]
    assert server.owned_pid() is None


def test_a_matching_listener_is_reused_and_not_stopped(tmp_path: Path):
    settings = _settings(tmp_path)
    starts: list[list[str]] = []
    argv = [str(settings.binary), "-m", str(settings.model)]
    server = LlamaServer(
        settings,
        popen=lambda _command, **_kwargs: starts.append(_command),
        port_open=lambda: True,
        listener_argv=lambda: argv,
    )
    server.ensure_started()
    server.stop()
    assert starts == []
    assert server.owned_pid() is None


def test_windows_command_line_parsing_keeps_quoted_paths():
    command = (
        r'"C:\Program Files\Urdu Translator\_internal\llama-server.exe" '
        r'-m "D:\Models\gemma-4-E4B_q4_0-it.gguf" -c 8192 --host 127.0.0.1 --port 8080'
    )
    argv = parse_windows_command_line(command)
    assert argv[0] == r"C:\Program Files\Urdu Translator\_internal\llama-server.exe"
    assert extract_model_argument(argv) == Path(r"D:\Models\gemma-4-E4B_q4_0-it.gguf")
    assert is_llama_server_executable(argv[0])


def test_compatible_listener_reuses_llama_server_from_another_install_path(tmp_path: Path):
    model = tmp_path / "gemma-4-E4B_q4_0-it.gguf"
    model.write_text("weights", encoding="utf-8")
    configured = tmp_path / "new-build" / "llama-server.exe"
    configured.parent.mkdir()
    configured.write_text("new", encoding="utf-8")
    previous = tmp_path / "Program Files" / "Urdu Translator" / "_internal" / "llama-server.exe"
    previous.parent.mkdir(parents=True)
    previous.write_text("old", encoding="utf-8")
    argv = [str(previous), "-m", str(model), "--host", "127.0.0.1", "--port", "8080"]
    assert compatible_listener(argv, configured, model) is True

    other_model = tmp_path / "other.gguf"
    other_model.write_text("other", encoding="utf-8")
    wrong = [str(previous), "-m", str(other_model)]
    assert compatible_listener(wrong, configured, model) is False
    assert compatible_listener(["C:\\Windows\\notepad.exe"], configured, model) is False


def test_a_previous_install_listener_is_reused_without_starting_another(tmp_path: Path):
    model = tmp_path / "gemma-4-E4B_q4_0-it.gguf"
    model.write_text("weights", encoding="utf-8")
    configured = tmp_path / "bundled" / "llama-server.exe"
    configured.parent.mkdir()
    configured.write_text("new", encoding="utf-8")
    previous = tmp_path / "old" / "llama-server.exe"
    previous.parent.mkdir()
    previous.write_text("old", encoding="utf-8")
    starts: list[list[str]] = []
    server = LlamaServer(
        ServerSettings(binary=configured, model=model),
        popen=lambda command, **_kwargs: starts.append(command),
        port_open=lambda: True,
        listener_argv=lambda: [str(previous), "-m", str(model)],
    )
    server.ensure_started()
    assert starts == []
    assert server.owned_pid() is None


def test_port_conflict_message_leaves_other_programs_running():
    message = port_conflict_message(8080, [r"C:\Tools\other.exe"])
    assert "already in use" in message
    assert "left running" in message
    assert "other.exe" in message


def test_an_unverified_listener_is_a_port_conflict(tmp_path: Path):
    settings = _settings(tmp_path)
    starts: list[list[str]] = []
    server = LlamaServer(
        settings,
        popen=lambda _command, **_kwargs: starts.append(_command),
        port_open=lambda: True,
        listener_argv=lambda: ["/usr/bin/other-server"],
    )
    with pytest.raises(TranslationFailedError, match="already in use"):
        server.ensure_started()
    assert starts == []


def test_shutdown_sends_term_then_kill_only_for_the_same_child(tmp_path: Path):
    settings = _settings(tmp_path)
    stubborn = StubbornProc()
    server = LlamaServer(settings, popen=lambda _command, **_kwargs: stubborn)
    server._process = stubborn
    server._owned = True
    server._owned_pid = stubborn.pid
    server.stop()
    assert stubborn.signals == ["term", "kill"]

    reused = ReusedPidProc(pid=99)
    other = LlamaServer(settings)
    other._process = reused
    other._owned = True
    other._owned_pid = 99
    other.stop()
    assert reused.signals == ["term"]


def test_reasoning_content_and_think_tags_are_removed():
    text = visible_translation(
        {
            "choices": [
                {
                    "message": {
                        "content": "<think>\nsecret plan\n</think>\nHello",
                        "reasoning_content": "secret plan",
                    }
                }
            ]
        }
    )
    assert text == "Hello"
    with pytest.raises(TranslationFailedError, match="Reasoning output is not shown"):
        visible_translation(
            {
                "choices": [
                    {
                        "message": {
                            "content": "<think>only this</think>",
                            "reasoning_content": "only this",
                        }
                    }
                ]
            }
        )


def test_cancellation_closes_the_connection_and_leaves_the_server_running(tmp_path: Path):
    settings = _settings(tmp_path)
    proc = FakeProc()
    connection = FakeConn()
    calls = {"n": 0}

    def should_stop() -> bool:
        calls["n"] += 1
        return calls["n"] > 2

    def exchange(method, path, _payload, _timeout, _should_stop):
        assert path == "/health"
        return 200, b"{}"

    server = LlamaServer(
        settings,
        popen=lambda _command, **_kwargs: proc,
        exchange=exchange,
        port_open=lambda: False,
        sleeper=lambda _seconds: None,
        connection_factory=lambda: connection,
    )
    server.ensure_started()
    server._exchange = None
    with pytest.raises(TranslationCancelled):
        server.complete("system", "user", should_stop=should_stop)
    assert connection.requested is True
    assert connection.closed is True
    assert proc.signals == []
    assert server.owned_pid() == proc.pid


def test_a_fake_process_translates_without_showing_reasoning(tmp_path: Path):
    settings = _settings(tmp_path)
    proc = FakeProc()
    starts: list[list[str]] = []

    def popen(command, **_kwargs):
        starts.append(list(command))
        return proc

    def exchange(method, path, payload, _timeout, _should_stop):
        if path == "/health":
            return 200, b"{}"
        assert method == "POST"
        assert path == "/v1/chat/completions"
        assert payload is not None
        body = json.dumps(
            {"choices": [{"message": {"content": "Peace", "reasoning_content": "hidden"}}]}
        ).encode("utf-8")
        return 200, body

    server = LlamaServer(
        settings,
        popen=popen,
        exchange=exchange,
        port_open=lambda: False,
        sleeper=lambda _seconds: None,
    )
    assert server.complete("system", "سلام") == "Peace"
    assert server.complete("system", "دوبارہ") == "Peace"
    assert len(starts) == 1
    assert proc.signals == []


@pytest.mark.skipif(
    os.environ.get("URDU_TRANSLATOR_LIVE_GEMMA") != "1",
    reason="Set URDU_TRANSLATOR_LIVE_GEMMA=1 to translate one line with the local server.",
)
def test_live_gemma_translates_one_synthetic_line():
    from urdu_translator.translation.loader import load_engine
    from urdu_translator.translation.service import translate_document

    root = Path(__file__).resolve().parents[1]
    try:
        result = translate_document("احمد: السلام علیکم", lambda: load_engine(root / "models"))
    finally:
        reset_for_tests()
    assert result.engine_name == "Gemma 4 E4B"
    assert result.text.startswith("Ahmed:")
    assert "think>" not in result.text.lower()
    assert "احمد" not in result.text
