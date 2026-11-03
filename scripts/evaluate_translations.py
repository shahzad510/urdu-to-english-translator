"""Translate the evaluation dataset with the local models and write a report.

The desktop application does not run this script. It does not download models.
It records Gemma output and time when the local GGUF can be loaded. OPUS-MT
and IndicTrans2 are reported as not run. The report does not score accuracy.

From the project root:

    python scripts/evaluate_translations.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from urdu_translator.evaluation.dataset import load_dataset
from urdu_translator.evaluation.report import write_results
from urdu_translator.evaluation.runner import run_local_models
from urdu_translator.paths import models_dir


def main() -> int:
    dataset_path = ROOT / "evaluation" / "datasets" / "conversations.json"
    results_path = ROOT / "evaluation" / "results" / "latest.json"
    report_path = ROOT / "evaluation" / "results" / "comparison.md"
    dataset = load_dataset(dataset_path)
    run = run_local_models(dataset, models_dir())
    write_results(run, results_path, report_path)
    print(f"Results: {results_path}")
    print(f"Report: {report_path}")
    if not run.indictrans2.loaded:
        print("IndicTrans2 did not run. Its column records the error and is not filled from OPUS-MT.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
