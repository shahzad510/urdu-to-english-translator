"""Evaluation records for the same Urdu text under two models.

A dataset stores the original Urdu, a reference English translation, room for
each model's output, and human notes. Running an evaluation writes a separate
results file so the reference text is not overwritten.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class EvalItem:
    """One Urdu source and the fields a person compares by hand."""

    id: str
    source_ur: str
    reference_en: str = ""
    opus_mt: str = ""
    indictrans2: str = ""
    gemma: str = ""
    notes: str = ""


@dataclass(frozen=True)
class EvalDataset:
    """A named list of evaluation items."""

    name: str
    items: list[EvalItem]
    description: str = ""


def load_dataset(path: Path) -> EvalDataset:
    """Read a dataset JSON file."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"Could not read {path}. {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not valid JSON. {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise ValueError(f"{path} must contain a name and a list of items.")
    name = str(data.get("name") or "").strip()
    if not name:
        raise ValueError(f"{path} needs a name.")
    items: list[EvalItem] = []
    for index, raw in enumerate(data["items"], start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"Item {index} in {path} must be an object.")
        source = str(raw.get("source_ur") or "")
        item_id = str(raw.get("id") or "").strip() or f"item-{index}"
        if not source.strip():
            raise ValueError(f"Item {item_id} needs original Urdu in source_ur.")
        items.append(
            EvalItem(
                id=item_id,
                source_ur=source,
                reference_en=str(raw.get("reference_en") or ""),
                opus_mt=str(raw.get("opus_mt") or ""),
                indictrans2=str(raw.get("indictrans2") or ""),
                gemma=str(raw.get("gemma") or ""),
                notes=str(raw.get("notes") or ""),
            )
        )
    return EvalDataset(name=name, items=items, description=str(data.get("description") or ""))


def dump_dataset(dataset: EvalDataset, path: Path) -> None:
    """Write a dataset, including any outputs and notes already filled in."""
    payload = {
        "name": dataset.name,
        "description": dataset.description,
        "fields": {
            "source_ur": "Original Urdu",
            "reference_en": "Reference English",
            "opus_mt": "OPUS-MT output",
            "indictrans2": "IndicTrans2 output",
            "gemma": "Gemma output",
            "notes": "Human evaluation notes",
        },
        "items": [asdict(item) for item in dataset.items],
    }
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
