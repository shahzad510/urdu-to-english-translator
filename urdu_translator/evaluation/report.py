"""Write a side-by-side comparison without scoring either model."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from urdu_translator.evaluation.runner import EvaluationRun, ItemResult, ModelStatus

NO_ACCURACY_CLAIM = (
    "This report lists the original Urdu, the reference English, the recorded model outputs, "
    "processing time, and errors. It does not measure translation accuracy and does not "
    "claim that any model is an improvement."
)


def render_report(run: EvaluationRun) -> str:
    """Markdown comparison. Reference text is shown for a person to read."""
    lines = [
        f"# {run.dataset_name}",
        "",
        NO_ACCURACY_CLAIM,
        "",
    ]
    if run.description:
        lines.extend([run.description, ""])
    lines.extend(_model_section("Gemma", run.gemma))
    lines.extend(_model_section("OPUS-MT", run.opus))
    lines.extend(_model_section("IndicTrans2", run.indictrans2))
    lines.extend(["## Items", ""])
    for item in run.items:
        lines.extend(_item_section(item))
    return "\n".join(lines).rstrip() + "\n"


def write_results(run: EvaluationRun, json_path: Path, report_path: Path) -> None:
    """Save the machine-readable results and the markdown report."""
    payload = {
        "dataset_name": run.dataset_name,
        "description": run.description,
        "accuracy_claim": False,
        "opus": asdict(run.opus),
        "indictrans2": asdict(run.indictrans2),
        "gemma": asdict(run.gemma),
        "items": [asdict(item) for item in run.items],
    }
    json_path = Path(json_path)
    report_path = Path(report_path)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_path.write_text(render_report(run), encoding="utf-8")


def _model_section(title: str, status: ModelStatus) -> list[str]:
    if status.loaded:
        seconds = "unknown" if status.load_seconds is None else f"{status.load_seconds:.2f} seconds"
        return [f"## {title}", "", f"Loaded ({status.backend}) in {seconds}.", ""]
    detail = status.error or "The model is not available."
    return [f"## {title}", "", f"Not run. {detail}", ""]


def _item_section(item: ItemResult) -> list[str]:
    lines = [f"### {item.id}", "", "Original Urdu:", "", _fence(item.source_ur), ""]
    if item.reference_en.strip():
        lines.extend(["Reference English:", "", _fence(item.reference_en), ""])
    else:
        lines.extend(["Reference English: none stored, so this item cannot be scored.", ""])
    lines.extend(_output_block("Gemma output", item.gemma, item.gemma_seconds, item.gemma_error))
    lines.extend(_output_block("OPUS-MT output", item.opus_mt, item.opus_mt_seconds, item.opus_mt_error))
    lines.extend(
        _output_block("IndicTrans2 output", item.indictrans2, item.indictrans2_seconds, item.indictrans2_error)
    )
    lines.extend(["Human evaluation notes:", "", item.notes.strip() or "(none)", ""])
    return lines


def _output_block(title: str, text: str, seconds: float | None, error: str) -> list[str]:
    if error:
        timing = "" if seconds is None else f" after {seconds:.2f} seconds"
        return [f"{title}: error{timing}.", "", error, ""]
    timing = "time not recorded" if seconds is None else f"{seconds:.2f} seconds"
    return [f"{title} ({timing}):", "", _fence(text), ""]


def _fence(text: str) -> str:
    return "```\n" + text.replace("```", "'''") + "\n```"
