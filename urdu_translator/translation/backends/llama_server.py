"""Local llama.cpp server used by the Gemma backend.

The process is started only for a translation. It listens on 127.0.0.1 and is
reused until the window closes. A server this application did not start is
left running. Python's own http.client talks to it; no HTTP package is added.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import http.client

from urdu_translator.errors import TranslationCancelled, TranslationFailedError

LOCAL_HOST = "127.0.0.1"
EXPECTED_GGUF = "gemma-4-E4B_q4_0-it.gguf"
HEALTH_TIMEOUT = 180.0
REQUEST_TIMEOUT = 120.0
STOP_TIMEOUT = 5.0

PopenFactory = Callable[..., subprocess.Popen]
Exchange = Callable[[str, str, dict | None, float, Callable[[], bool] | None], tuple[int, bytes]]
PortProbe = Callable[[], bool]
ListenerLookup = Callable[[], list[str] | None]
Sleeper = Callable[[float], None]
StopCheck = Callable[[], bool]

_LOCK = threading.Lock()
_SERVER: LlamaServer | None = None


@dataclass(frozen=True)
class ServerSettings:
    """The verified local server settings."""

    binary: Path
    model: Path
    host: str = LOCAL_HOST
    port: int = 8080
    context: int = 8192
    threads: int = 4
    temperature: float = 0.2
    max_new_tokens: int = 2048
    health_timeout: float = HEALTH_TIMEOUT
    request_timeout: float = REQUEST_TIMEOUT
    stop_timeout: float = STOP_TIMEOUT


def server_command(settings: ServerSettings) -> list[str]:
    """Build the llama-server command from the verified arguments."""
    if settings.host != LOCAL_HOST:
        raise TranslationFailedError("The translation server listens on 127.0.0.1 only.")
    return [
        str(settings.binary),
        "-m",
        str(settings.model),
        "-c",
        str(settings.context),
        "-t",
        str(settings.threads),
        "--reasoning",
        "off",
        "--host",
        LOCAL_HOST,
        "--port",
        str(settings.port),
    ]


def missing_model_message(model: Path) -> str:
    """Explain that the external Gemma file cannot be read."""
    return (
        f"The external drive or model file is unavailable: {EXPECTED_GGUF}. "
        f"Checked {model}. Connect the drive that contains this file. "
        "The application does not download weights and does not use another translation engine."
    )


def missing_binary_message(binary: Path) -> str:
    """Explain that llama-server cannot be started."""
    return (
        f"The llama-server program is unavailable: {binary}. "
        "The application does not download it and does not use another translation engine."
    )


def check_files(model: Path, binary: Path) -> None:
    """Raise before a process is started when either external file is missing."""
    if not model.is_file():
        raise TranslationFailedError(missing_model_message(model))
    if not binary.is_file():
        raise TranslationFailedError(missing_binary_message(binary))


def visible_translation(payload: dict) -> str:
    """Return reply text, without reasoning content or think tags."""
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise TranslationFailedError("The translation model returned no text.")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise TranslationFailedError("The translation model returned no text.")
    text = _content_text(message.get("content"))
    text = _strip_think_spans(text)
    if not text.strip():
        raise TranslationFailedError(
            "The translation model returned no translation text. Reasoning output is not shown."
        )
    return text.strip()


class LlamaServer:
    """One llama-server process, or a matching server already listening locally."""

    def __init__(
        self,
        settings: ServerSettings,
        *,
        popen: PopenFactory | None = None,
        exchange: Exchange | None = None,
        port_open: PortProbe | None = None,
        listener_argv: ListenerLookup | None = None,
        sleeper: Sleeper | None = None,
        connection_factory: Callable[[], http.client.HTTPConnection] | None = None,
    ) -> None:
        self.settings = settings
        self._popen = popen or subprocess.Popen
        self._exchange = exchange
        self._port_open = port_open
        self._listener_argv = listener_argv
        self._sleep = sleeper or time.sleep
        self._connection_factory = connection_factory
        self._process: subprocess.Popen | None = None
        self._owned = False
        self._owned_pid: int | None = None
        self._guard = threading.Lock()

    def matches(self, settings: ServerSettings) -> bool:
        return (
            self.settings.binary == settings.binary
            and self.settings.model == settings.model
            and self.settings.host == settings.host
            and self.settings.port == settings.port
            and self.settings.context == settings.context
            and self.settings.threads == settings.threads
        )

    def ensure_started(self) -> None:
        """Start the server, or reuse a verified one. Do not start it twice."""
        with self._guard:
            if self._process is not None and self._process.poll() is None:
                return
            self._process = None
            self._owned = False
            self._owned_pid = None
            if self._endpoint_open():
                argv = self._listener()
                if argv is not None and _command_matches(argv, self.settings.binary, self.settings.model):
                    return
                raise TranslationFailedError(
                    f"Port {self.settings.port} on {LOCAL_HOST} is already in use. "
                    "The program listening there is not the configured llama-server "
                    "and model, so it was left running."
                )
            check_files(self.settings.model, self.settings.binary)
            self._spawn()
            try:
                self._wait_until_healthy()
            except Exception:
                process, owned, pid = self._detach()
                self._terminate(process, owned, pid, self.settings.stop_timeout)
                raise

    def complete(self, system: str, user: str, should_stop: StopCheck | None = None) -> str:
        """Send one chat request and return the visible translation."""
        self.ensure_started()
        if should_stop is not None and should_stop():
            raise TranslationCancelled("Translation was cancelled.")
        status, body = self._request(
            "POST",
            "/v1/chat/completions",
            _chat_payload(system, user, self.settings),
            should_stop,
            self.settings.request_timeout,
        )
        if status != 200:
            raise TranslationFailedError(f"The translation server returned status {status}.")
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise TranslationFailedError("The translation server returned unreadable text.") from exc
        if not isinstance(payload, dict):
            raise TranslationFailedError("The translation server returned unreadable text.")
        return visible_translation(payload)

    def stop(self) -> None:
        """Stop the child this object started. Another listener is left alone."""
        with self._guard:
            process, owned, pid = self._detach()
        self._terminate(process, owned, pid, self.settings.stop_timeout)

    def _detach(self) -> tuple[subprocess.Popen | None, bool, int | None]:
        process = self._process
        owned = self._owned
        pid = self._owned_pid
        self._process = None
        self._owned = False
        self._owned_pid = None
        return process, owned, pid

    @staticmethod
    def _terminate(
        process: subprocess.Popen | None,
        owned: bool,
        pid: int | None,
        timeout: float,
    ) -> None:
        if not owned or process is None or pid is None:
            return
        if process.poll() is not None or process.pid != pid:
            return
        process.terminate()
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            if process.poll() is None and process.pid == pid:
                process.kill()
                try:
                    process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    return

    def owned_pid(self) -> int | None:
        """Pid of the running child this application started, if it still owns one."""
        process = self._process
        if not self._owned or process is None or process.poll() is not None:
            return None
        return self._owned_pid

    def _spawn(self) -> None:
        env = os.environ.copy()
        env["HF_HUB_OFFLINE"] = "1"
        kwargs: dict = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "stdin": subprocess.DEVNULL,
            "start_new_session": True,
            "env": env,
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            process = self._popen(server_command(self.settings), **kwargs)
        except OSError as exc:
            raise TranslationFailedError(
                f"{missing_binary_message(self.settings.binary)} {exc}"
            ) from exc
        self._process = process
        self._owned = True
        self._owned_pid = process.pid

    def _wait_until_healthy(self) -> None:
        deadline = time.monotonic() + self.settings.health_timeout
        while time.monotonic() < deadline:
            process = self._process
            if process is not None and process.poll() is not None:
                raise TranslationFailedError("The translation server stopped before it was ready.")
            try:
                status, _body = self._request("GET", "/health", None, None, 3)
            except OSError:
                status = 0
            if status == 200:
                return
            self._sleep(0.25)
        raise TranslationFailedError("The translation server did not become ready in time.")

    def _endpoint_open(self) -> bool:
        if self._port_open is not None:
            return self._port_open()
        return _tcp_open(self.settings.host, self.settings.port)

    def _listener(self) -> list[str] | None:
        if self._listener_argv is not None:
            return self._listener_argv()
        return listening_command(self.settings.host, self.settings.port)

    def _request(
        self,
        method: str,
        path: str,
        payload: dict | None,
        should_stop: StopCheck | None,
        timeout: float,
    ) -> tuple[int, bytes]:
        if should_stop is not None and should_stop():
            raise TranslationCancelled("Translation was cancelled.")
        if self._exchange is not None:
            return self._exchange(method, path, payload, timeout, should_stop)
        return self._http(method, path, payload, should_stop, timeout)

    def _http(
        self,
        method: str,
        path: str,
        payload: dict | None,
        should_stop: StopCheck | None,
        timeout: float,
    ) -> tuple[int, bytes]:
        connection = self._open_connection()
        try:
            body = None if payload is None else json.dumps(payload).encode("utf-8")
            headers = {"Content-Type": "application/json"} if body is not None else {}
            connection.request(method, path, body=body, headers=headers)
            deadline = time.monotonic() + timeout
            while True:
                if should_stop is not None and should_stop():
                    connection.close()
                    raise TranslationCancelled("Translation was cancelled.")
                if time.monotonic() > deadline:
                    connection.close()
                    raise TranslationFailedError("The translation server did not answer in time.")
                try:
                    response = connection.getresponse()
                    break
                except TimeoutError:
                    continue
            raw = response.read()
            return response.status, raw
        finally:
            connection.close()

    def _open_connection(self) -> http.client.HTTPConnection:
        if self._connection_factory is not None:
            return self._connection_factory()
        if self.settings.host != LOCAL_HOST:
            raise TranslationFailedError("The translation server listens on 127.0.0.1 only.")
        return http.client.HTTPConnection(LOCAL_HOST, self.settings.port, timeout=1)


def shared_server(settings: ServerSettings) -> LlamaServer:
    """Return the session server, replacing it when the configuration changes."""
    global _SERVER
    with _LOCK:
        if _SERVER is not None and _SERVER.matches(settings):
            return _SERVER
        if _SERVER is not None:
            _SERVER.stop()
        _SERVER = LlamaServer(settings)
        return _SERVER


def stop_owned_server() -> None:
    """Stop the llama-server child started by this application."""
    with _LOCK:
        if _SERVER is not None:
            _SERVER.stop()


def owned_process_pid() -> int | None:
    """Pid started by this application, or None when no child is owned."""
    with _LOCK:
        if _SERVER is None:
            return None
        return _SERVER.owned_pid()


def reset_for_tests() -> None:
    """Drop the session server. Tests use this so a real process is not started."""
    global _SERVER
    with _LOCK:
        if _SERVER is not None:
            _SERVER.stop()
        _SERVER = None


def listening_command(host: str, port: int) -> list[str] | None:
    """Return the command line of the process listening on host:port, when it can be read."""
    if host != LOCAL_HOST:
        return None
    inode = _listen_inode(port)
    if inode is None:
        return None
    needle = f"socket:[{inode}]"
    proc = Path("/proc")
    if not proc.is_dir():
        return None
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        fd_dir = entry / "fd"
        try:
            descriptors = list(fd_dir.iterdir())
        except OSError:
            continue
        for descriptor in descriptors:
            try:
                if os.readlink(descriptor) != needle:
                    continue
            except OSError:
                continue
            try:
                raw = (entry / "cmdline").read_bytes()
            except OSError:
                return None
            return [part.decode("utf-8", "replace") for part in raw.split(b"\0") if part]
    return None


def _listen_inode(port: int) -> str | None:
    tcp = Path("/proc/net/tcp")
    if not tcp.is_file():
        return None
    needle = f"{_ipv4_hex(LOCAL_HOST)}:{port:04X}"
    try:
        lines = tcp.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines[1:]:
        fields = line.split()
        if len(fields) < 10:
            continue
        if fields[1].upper() == needle and fields[3] == "0A":
            return fields[9]
    return None


def _ipv4_hex(host: str) -> str:
    numbers = [int(part) for part in host.split(".")]
    return f"{numbers[3]:02X}{numbers[2]:02X}{numbers[1]:02X}{numbers[0]:02X}"


def _tcp_open(host: str, port: int) -> bool:
    if host != LOCAL_HOST:
        return False
    connection = http.client.HTTPConnection(LOCAL_HOST, port, timeout=2)
    try:
        connection.connect()
    except OSError:
        return False
    else:
        return True
    finally:
        connection.close()


def _command_matches(argv: list[str], binary: Path, model: Path) -> bool:
    if not argv:
        return False
    try:
        same_binary = Path(argv[0]).resolve() == binary.resolve()
    except OSError:
        same_binary = False
    model_text = ""
    for flag in ("-m", "--model"):
        if flag in argv:
            index = argv.index(flag)
            if index + 1 < len(argv):
                model_text = argv[index + 1]
                break
    if not model_text:
        return False
    try:
        same_model = Path(model_text).resolve() == model.resolve()
    except OSError:
        same_model = False
    return same_binary and same_model


def _chat_payload(system: str, user: str, settings: ServerSettings) -> dict:
    return {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": settings.temperature,
        "max_tokens": settings.max_new_tokens,
    }


def _content_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        bits: list[str] = []
        for part in content:
            if isinstance(part, str):
                bits.append(part)
            elif isinstance(part, dict) and isinstance(part.get("text"), str):
                bits.append(str(part["text"]))
        return "\n".join(bits)
    return ""


def _strip_think_spans(text: str) -> str:
    start = "<" + "think" + ">"
    end = "</" + "think" + ">"
    while True:
        opening = text.lower().find(start)
        if opening < 0:
            return text
        closing = text.lower().find(end, opening + len(start))
        if closing < 0:
            return text
        text = text[:opening] + text[closing + len(end) :]
