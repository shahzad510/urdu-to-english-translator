"""The application source stays offline."""

import re
from pathlib import Path

_FORBIDDEN = re.compile(
    r"requests|httpx|aiohttp|urllib|http\.client|QNetworkAccessManager|huggingface|socket\.|import socket",
    re.IGNORECASE,
)


def test_application_source_does_not_reference_network_clients():
    root = Path(__file__).resolve().parents[1] / "urdu_translator"
    allowed = Path("translation/backends/llama_server.py")
    offenders: list[str] = []
    for path in root.rglob("*.py"):
        relative = path.relative_to(root)
        if relative == allowed:
            continue
        text = path.read_text(encoding="utf-8")
        if _FORBIDDEN.search(text):
            offenders.append(str(relative))
    assert offenders == []
    server = (root / allowed).read_text(encoding="utf-8")
    assert "http.client" in server
    assert "127.0.0.1" in server
    assert "huggingface" not in server.lower()
    assert "requests" not in server
    assert "--hf-repo" not in server
