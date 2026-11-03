"""Check or, only when asked, copy the official Gemma 4 E4B GGUF.

From the project root, this prints the local status and does not download:

    python scripts/fetch_gemma.py

Copy the weights only when you pass --download, while online, after reading
models/gemma-4-e4b/NOTICE.txt:

    python scripts/fetch_gemma.py --download

Expected download: the official Google Q4_0 GGUF, about 4.5 GB. Licence:
Apache 2.0 on the Gemma 4 model card. Keep the official licence and notices
with the files. Allow extra RAM beyond the weights for the runtime and the
8192-token context cache.

The desktop application never runs this script.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from urdu_translator.translation.backends.gemma import local_install_report

DESTINATION = ROOT / "models" / "gemma-4-e4b"
REPO_ID = "google/gemma-4-E4B-it-qat-q4_0-gguf"


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--download" not in args:
        print(local_install_report(DESTINATION))
        print("No files were downloaded. Re-run with --download only when you want the weights copied.")
        return 0
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("Install huggingface_hub in the environment used for this one-time copy.", file=sys.stderr)
        return 1
    DESTINATION.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=REPO_ID,
        local_dir=str(DESTINATION),
        local_dir_use_symlinks=False,
    )
    print(f"Weight files are in {DESTINATION}")
    print("Keep the official licence and notices in that folder.")
    print("Install llama-cpp-python from requirements-gemma.txt before translating.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
