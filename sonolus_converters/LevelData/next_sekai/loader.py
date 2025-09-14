import json, gzip
from typing import IO, Literal

from ...notes.score import Score
from ...notes.metadata import MetaData
from ...notes.bpm import Bpm
from ...notes.timescale import TimeScaleGroup, TimeScalePoint
from ...notes.single import Single
from ...notes.slide import Slide, SlideStartPoint, SlideRelayPoint, SlideEndPoint
from ...notes.guide import Guide, GuidePoint

from ...archetypes import EngineArchetypeName, EngineArchetypeDataName


def load(fp: IO) -> Score:
    raise NotImplementedError("NextSekai support loading is too hard...")
    """Load a next_sekai LevelData file and convert it to a Score object."""
    # check first 2 bytes of possible gzip
    start = fp.peek(2) if hasattr(fp, "peek") else fp.read(2)
    if not hasattr(fp, "peek"):
        fp.seek(0)  # set pointer back to start
    if start[:2] == b"\x1f\x8b":  # GZIP magic number
        with gzip.GzipFile(fileobj=fp, mode="rb") as gz:
            leveldata = json.load(gz)
    else:
        leveldata = json.load(fp)

    metadata = MetaData(
        title="",
        artist="",
        designer="",
        waveoffset=leveldata.get("bgmOffset", 0),
        requests=["ticks_per_beat 480"],
    )

    notes = []
