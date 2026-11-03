"""Copy the selected OPUS-MT weights into the local model folder.

Run this once while online, from the project root:

    python scripts/fetch_opus_mt.py

The desktop application never runs this script and never downloads weights.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ID = "Helsinki-NLP/opus-mt-ur-en"
DESTINATION = Path(__file__).resolve().parents[1] / "models" / "opus-mt-ur-en"


def main() -> int:
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("Install huggingface_hub in the environment used for this one-time copy.", file=sys.stderr)
        return 1
    DESTINATION.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=REPO_ID,
        local_dir=str(DESTINATION),
        ignore_patterns=["*.h5", "*.msgpack", "*.ot", "tf_model*"],
    )
    print(f"Weight files are in {DESTINATION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
