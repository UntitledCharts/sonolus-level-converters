import json, gzip
from dataclasses import dataclass, asdict
from typing import Dict, List, Union, Optional, Literal

import base36

from ...notes.score import Score
from ...notes.metadata import MetaData
from ...notes.bpm import Bpm
from ...notes.timescale import TimeScaleGroup, TimeScalePoint
from ...notes.single import Single
from ...notes.slide import Slide, SlideStartPoint, SlideRelayPoint, SlideEndPoint
from ...notes.guide import Guide, GuidePoint

from ...archetypes import EngineArchetypeName, EngineArchetypeDataName
from ...level import LevelData, LevelDataEntity


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


def export(path: str, score: Score, as_compressed: bool = True):
    if not any(isinstance(note, Bpm) for note in score.notes):
        score.notes.insert(0, Bpm(beat=round(0, 6), bpm=160.0))

    entities = [asdict(entity) for entity in entities]
    _remove_none(entities)

    # dump LevelData
    leveldata: LevelData = {
        "bgmOffset": score.metadata.waveoffset,
        "entities": entities,
    }

    if not as_compressed:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(leveldata, f, indent=4, ensure_ascii=False)
    else:
        data = json.dumps(leveldata, ensure_ascii=False, separators=(",", ":"))
        encoded = data.encode("utf-8")
        with gzip.open(f"{path}.gz", "wb") as f:
            f.write(encoded)
