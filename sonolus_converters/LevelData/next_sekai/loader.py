import json, gzip
from typing import IO, Literal

from ...notes.score import Score
from ...notes.metadata import MetaData
from ...notes.bpm import Bpm
from ...notes.timescale import TimeScaleGroup, TimeScalePoint
from ...notes.single import Single
from ...notes.slide import Slide, SlideStartPoint, SlideRelayPoint, SlideEndPoint
from ...notes.guide import Guide, GuidePoint

from ...notes.engine.archetypes import EngineArchetypeName, EngineArchetypeDataName


def load(fp: IO) -> Score:
    # NOTE: for those attempting this
    # you are free to add more values and note types
    # however, make sure you map them to something normal in every other exporter!
    # this can be as simple as making a function to replace any super extended features
    # for example, any down flicks -> omni up flicks
    # or, deleting fake notes entirely
    raise NotImplementedError(
        "Feel free to open a pull request and implement! MMW4CC USC -> PySekai/NextSekai LevelData"
    )
