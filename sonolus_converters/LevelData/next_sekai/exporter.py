import json, gzip
from dataclasses import dataclass, asdict
from pathlib import Path
import io
from typing import Dict, List, Union, Optional, Callable, Literal, IO, NamedTuple, Any

import base36

from ...notes.score import Score
from ...notes.metadata import MetaData
from ...notes.bpm import Bpm
from ...notes.timescale import TimeScaleGroup, TimeScalePoint
from ...notes.single import Single
from ...notes.slide import Slide, SlideStartPoint, SlideRelayPoint, SlideEndPoint
from ...notes.guide import Guide, GuidePoint

from ...notes.engine.archetypes import EngineArchetypeName, EngineArchetypeDataName


def export(
    path: Union[str, Path, bytes, io.BytesIO, IO[bytes]],
    score: Score,
    as_compressed: bool = True,
):

    raise NotImplementedError("I gave up.")

    leveldata: LevelData = {
        "bgmOffset": level_data.bgm_offset,
        "entities": [
            {
                "name": level_refs[entity],
                "archetype": entity.name,
                "data": entity._level_data_entries(level_refs),
            }
            for entity in level_data.entities
        ],
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
