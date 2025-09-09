import json
from dataclasses import asdict
from ..notes.score import Score


def _remove_none(data):
    if isinstance(data, dict):
        for key, val in data.copy().items():
            if val is None:
                del data[key]
            _remove_none(val)

    elif isinstance(data, list):
        for obj in data:
            _remove_none(obj)


def export(path: str, score: Score):
    notes = [asdict(i) for i in score.notes]
    _remove_none(notes)

    usc_data = {
        "usc": {"objects": notes, "offset": score.metadata.waveoffset},
        "version": 2,
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(usc_data, f, indent=4, ensure_ascii=False)
