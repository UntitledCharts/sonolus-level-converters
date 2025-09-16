import json, gzip
from dataclasses import dataclass, asdict
from pathlib import Path
import io
from typing import Dict, List, Union, Optional, Callable, Literal, IO

import base36

from ...notes.score import Score
from ...notes.metadata import MetaData
from ...notes.bpm import Bpm
from ...notes.timescale import TimeScaleGroup, TimeScalePoint
from ...notes.single import Single
from ...notes.slide import Slide, SlideStartPoint, SlideRelayPoint, SlideEndPoint
from ...notes.guide import Guide, GuidePoint

from ...notes.engine.archetypes import EngineArchetypeName, EngineArchetypeDataName
from ...notes.engine.level import LevelData, LevelDataEntity


def _remove_none(data):
    if isinstance(data, dict):
        for key, val in list(data.items()):
            if val is None:
                del data[key]
            else:
                _remove_none(val)
    elif isinstance(data, list):
        for obj in data:
            _remove_none(obj)


def export(
    path: Union[str, Path, bytes, io.BytesIO, IO[bytes]],
    score: Score,
    as_compressed: bool = True,
):
    if not any(isinstance(note, Bpm) for note in score.notes):
        score.notes.insert(0, Bpm(beat=round(0, 6), bpm=160.0))

    raise NotImplementedError()

    entities = [asdict(entity) for entity in entities]
    _remove_none(entities)

    # dump LevelData
    leveldata: LevelData = {
        "bgmOffset": score.metadata.waveoffset,
        "entities": entities,
    }

    if isinstance(path, (str, Path)):
        path = Path(path)
        if not as_compressed:
            with path.open("w", encoding="utf-8") as f:
                json.dump(leveldata, f, indent=4, ensure_ascii=False)
        else:
            with gzip.open(f"{path}.gz", "wb") as f:
                data = json.dumps(
                    leveldata, ensure_ascii=False, separators=(",", ":")
                ).encode("utf-8")
                f.write(data)
    elif isinstance(path, io.BytesIO) or (
        hasattr(path, "write") and callable(path.write)
    ):
        if not as_compressed:
            json_text = json.dumps(leveldata, indent=4, ensure_ascii=False)
            path.write(json_text.encode("utf-8"))
        else:
            data = json.dumps(
                leveldata, ensure_ascii=False, separators=(",", ":")
            ).encode("utf-8")
            with gzip.GzipFile(fileobj=path, mode="wb", mtime=0) as f:
                f.write(data)
