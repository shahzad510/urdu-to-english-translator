"""The comparison runner records both models and does not score them."""

from pathlib import Path

from urdu_translator.evaluation.dataset import EvalDataset, EvalItem, dump_dataset, load_dataset
from urdu_translator.evaluation.report import NO_ACCURACY_CLAIM, render_report, write_results
from urdu_translator.evaluation.runner import ModelStatus, evaluate_dataset
from urdu_translator.translation.backends.indictrans2 import local_install_report


def test_dataset_round_trip_keeps_reference_output_and_notes(tmp_path: Path):
    source = EvalDataset(
        name="Sample",
        description="A short set",
        items=[
            EvalItem(
                id="greet",
                source_ur="سلام",
                reference_en="Hello",
                notes="Watch the greeting.",
            )
        ],
    )
    path = tmp_path / "set.json"
    dump_dataset(source, path)
    loaded = load_dataset(path)
    assert loaded.items[0].reference_en == "Hello"
    assert loaded.items[0].notes == "Watch the greeting."
    assert loaded.items[0].opus_mt == ""
    assert loaded.items[0].indictrans2 == ""


def test_both_translators_are_timed_and_the_report_makes_no_accuracy_claim(tmp_path: Path):
    dataset = EvalDataset(
        name="Sample",
        items=[EvalItem(id="greet", source_ur="سلام", reference_en="Hello", notes="Human note")],
    )
    run = evaluate_dataset(
        dataset,
        opus=lambda text: f"opus {text}",
        indictrans2=lambda text: f"indic {text}",
        opus_status=ModelStatus("marian", True, 0.25, ""),
        indictrans2_status=ModelStatus("indictrans2", True, 0.5, ""),
    )
    item = run.items[0]
    assert item.opus_mt == "opus سلام"
    assert item.indictrans2 == "indic سلام"
    assert item.gemma == ""
    assert item.gemma_error
    assert item.opus_mt_seconds is not None and item.opus_mt_seconds >= 0
    assert item.indictrans2_seconds is not None
    assert item.notes == "Human note"
    report = render_report(run)
    assert NO_ACCURACY_CLAIM in report
    assert "Hello" in report
    assert "opus سلام" in report
    assert "indic سلام" in report
    assert "better" not in report.lower()

    results = tmp_path / "latest.json"
    written = tmp_path / "comparison.md"
    write_results(run, results, written)
    assert "accuracy_claim" in results.read_text(encoding="utf-8")
    assert NO_ACCURACY_CLAIM in written.read_text(encoding="utf-8")


def test_a_missing_indictrans_model_is_recorded_and_not_filled_from_opus():
    dataset = load_dataset(Path("evaluation/datasets/conversations.json"))
    run = evaluate_dataset(
        dataset,
        opus=lambda text: f"opus:{text.splitlines()[0]}",
        indictrans2=None,
        opus_status=ModelStatus("marian", True, 1.0, ""),
        indictrans2_status=ModelStatus("indictrans2", False, None, "Weights are not installed."),
    )
    assert run.items[0].id == "greeting-exchange"
    assert run.items[0].opus_mt.startswith("opus:")
    assert run.items[0].indictrans2 == ""
    assert run.items[0].indictrans2_error == "Weights are not installed."
    assert "North market" in run.items[0].reference_en
    report = render_report(run)
    assert "Weights are not installed." in report
    assert "Not run." in report


def test_one_model_error_does_not_drop_the_other_output():
    dataset = EvalDataset(name="Sample", items=[EvalItem(id="one", source_ur="ہاں", reference_en="Yes")])

    def fail_opus(_text: str) -> str:
        raise RuntimeError("opus failed")

    run = evaluate_dataset(
        dataset,
        opus=fail_opus,
        indictrans2=lambda _text: "Yes.",
        opus_status=ModelStatus("marian", True, 0.1, ""),
        indictrans2_status=ModelStatus("indictrans2", True, 0.1, ""),
    )
    assert run.items[0].opus_mt == ""
    assert "opus failed" in run.items[0].opus_mt_error
    assert run.items[0].indictrans2 == "Yes."
    assert run.items[0].indictrans2_error == ""


def test_install_report_does_not_claim_the_weights_are_present():
    report = local_install_report(Path("models/indictrans2-indic-en"))
    assert "MIT" in report
    assert "does not download" in report
    assert "not installed" in report
    assert "about 1 GB" in report
