"""Check or, only when asked, copy IndicTrans2 into the local model folder.

From the project root, this prints the local status and does not download:

    python scripts/fetch_indictrans2.py

Copy the weights only when you pass --download, while online, after reading
docs/indictrans2-install.md:

    python scripts/fetch_indictrans2.py --download

Expected download: about 1 GB. Licence: MIT (AI4Bharat). Allow about 3–4 GB
of RAM when the application later loads the model.

The desktop application never runs this script.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from urdu_translator.translation.backends.indictrans2 import local_install_report

DESTINATION = ROOT / "models" / "indictrans2-indic-en"
REPO_ID = "ai4bharat/indictrans2-indic-en-dist-200M"


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
        ignore_patterns=["*.h5", "*.msgpack", "*.ot", "tf_model*", "*.gguf"],
    )
    print(f"Weight files are in {DESTINATION}")
    print("Install IndicTransToolkit in the same environment before translating.")
    print("Keep engine.json and NOTICE.txt in that folder.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
