"""Side-by-side evaluation of the local Urdu-to-English models."""

from urdu_translator.evaluation.dataset import EvalDataset, EvalItem, dump_dataset, load_dataset
from urdu_translator.evaluation.report import NO_ACCURACY_CLAIM, render_report, write_results
from urdu_translator.evaluation.runner import EvaluationRun, evaluate_dataset, run_local_models

__all__ = [
    "EvalDataset",
    "EvalItem",
    "EvaluationRun",
    "NO_ACCURACY_CLAIM",
    "dump_dataset",
    "evaluate_dataset",
    "load_dataset",
    "render_report",
    "run_local_models",
    "write_results",
]
