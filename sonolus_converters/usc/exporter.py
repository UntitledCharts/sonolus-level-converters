import json
from dataclasses import asdict
from ..notes.score import Score
from ..notes.bpm import Bpm


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
    if not any(isinstance(note, Bpm) for note in score.notes):
        score.notes.insert(0, Bpm(beat=round(0, 6), bpm=160.0))
    notes = [asdict(i) for i in score.notes]
    _remove_none(notes)

    usc_data = {
        "usc": {"objects": notes, "offset": score.metadata.waveoffset},
        "version": 2,
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(usc_data, f, indent=4, ensure_ascii=False)
