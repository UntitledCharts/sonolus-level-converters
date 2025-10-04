import json
from dataclasses import asdict
from ..notes.score import Score, usc_remove_fake_field
from ..notes.bpm import Bpm

from ..utils import SinglePrecisionFloatEncoder

from pathlib import Path
import io
from typing import Union


def _remove_none(data):
    if isinstance(data, dict):
        for key, val in data.copy().items():
            if val is None:
                del data[key]
            _remove_none(val)

    elif isinstance(data, list):
        for obj in data:
            _remove_none(obj)


def export(
    path: Union[str, Path, io.BytesIO, io.StringIO, io.TextIOBase],
    score: Score,
    minified: bool = True,
):
    if not any(isinstance(note, Bpm) for note in score.notes):
        score.notes.insert(0, Bpm(beat=round(0, 6), bpm=160.0))
    notes = [asdict(i) for i in score.notes]
    _remove_none(notes)
    usc_remove_fake_field(notes)

    usc_data = {
        "usc": {"objects": notes, "offset": score.metadata.waveoffset},
        "version": 2,
    }

    if isinstance(path, (str, Path)):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(
                usc_data,
                f,
                indent=None if minified else 4,
                ensure_ascii=False,
                cls=SinglePrecisionFloatEncoder,
            )
    elif isinstance(path, (io.StringIO, io.TextIOBase)):
        json.dump(
            usc_data,
            path,
            indent=None if minified else 4,
            ensure_ascii=False,
            cls=SinglePrecisionFloatEncoder,
        )
        path.seek(0)
    elif isinstance(path, io.BytesIO):
        json_text = json.dumps(
            usc_data,
            indent=None if minified else 4,
            ensure_ascii=False,
            cls=SinglePrecisionFloatEncoder,
        )
        path.write(json_text.encode("utf-8"))
        path.seek(0)
    else:
        raise TypeError(f"Unsupported path type: {type(path)}")
