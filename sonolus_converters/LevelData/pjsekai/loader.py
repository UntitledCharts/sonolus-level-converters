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
    """Load a pjsekai LevelData file and convert it to a Score object."""
    # check first 2 bytes of possible gzip
    start = fp.peek(2) if hasattr(fp, "peek") else fp.read(2)
    if not hasattr(fp, "peek"):
        fp.seek(0)  # set pointer back to start
    if start[:2] == b"\x1f\x8b":  # GZIP magic number
        with gzip.GzipFile(fileobj=fp, mode="rb", mtime=0) as gz:
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

    # Restore metadata (if present in future, currently only bgmOffset)
    metadata = MetaData(
        title="",
        artist="",
        designer="",
        waveoffset=leveldata.get("bgmOffset", 0),
        requests=["ticks_per_beat 480"],
    )

    notes = []
    directions = {
        -1: "left",
        0: "up",
        1: "right",
    }
    eases = {
        -1: "out",
        0: "linear",
        1: "in",
    }
    has_bpm = False

    for entity in leveldata.get("entities", []):
        archetype = entity.get("archetype")
        data = {d["name"]: d.get("value", d.get("ref")) for d in entity.get("data", [])}

        # Skip SimLine entities

        if archetype == "SimLine":
            continue

        if archetype == EngineArchetypeName.BpmChange:
            notes.append(
                Bpm(
                    beat=round(data[EngineArchetypeDataName.Beat], 6),
                    bpm=data[EngineArchetypeDataName.Bpm],
                )
            )
            has_bpm = True
        elif archetype == EngineArchetypeName.TimeScaleChange:
            group = TimeScaleGroup()
            group.append(
                TimeScalePoint(
                    beat=round(data[EngineArchetypeDataName.Beat], 6),
                    timeScale=data[EngineArchetypeDataName.TimeScale],
                )
            )
            notes.append(group)
        elif "connections" in data:
            connections = data["connections"]
            if archetype == "IgnoredSlideTickNote":
                guide = Guide(
                    color=data.get("color", "yellow"), fade=data.get("fade", 0)
                )
                for point in connections:
                    guide.append(
                        GuidePoint(
                            beat=round(point.get(EngineArchetypeDataName.Beat, 0), 6),
                            ease=point.get("ease"),
                            lane=point.get("lane", 0),
                            size=point.get("size", 1),
                            timeScaleGroup=0,
                        )
                    )
                notes.append(guide)
            else:
                slide = Slide(critical="Critical" in archetype)
                for point in connections:
                    pt_type = point.get("type", "tick")
                    common_args = dict(
                        beat=round(point.get(EngineArchetypeDataName.Beat, 0), 6),
                        lane=point.get("lane", 0),
                        size=point.get("size", 1),
                        timeScaleGroup=0,
                    )
                    if pt_type == "start":
                        slide.append(
                            SlideStartPoint(
                                **common_args,
                                critical=point.get("critical", False),
                                ease=point.get("ease"),
                                judgeType=point.get("judgeType"),
                            )
                        )
                    elif pt_type in ("tick", "attach"):
                        slide.append(
                            SlideRelayPoint(
                                **common_args,
                                type=pt_type,
                                critical=point.get("critical", False),
                                ease=point.get("ease"),
                            )
                        )
                    elif pt_type == "end":
                        slide.append(
                            SlideEndPoint(
                                **common_args,
                                critical=point.get("critical", False),
                                judgeType=point.get("judgeType"),
                                direction=point.get("direction"),
                            )
                        )
                notes.append(slide)
        elif "midpoints" in data:
            guide = Guide(color=data.get("color", "yellow"), fade=data.get("fade", 0))
            for point in data["midpoints"]:
                guide.append(
                    GuidePoint(
                        beat=round(point.get(EngineArchetypeDataName.Beat, 0), 6),
                        ease=point.get("ease"),
                        lane=point.get("lane", 0),
                        size=point.get("size", 1),
                        timeScaleGroup=0,
                    )
                )
            notes.append(guide)
        elif archetype in [
            "NormalTapNote",
            "CriticalTapNote",
            "NormalFlickNote",
            "CriticalFlickNote",
            "NormalTraceNote",
            "CriticalTraceNote",
        ]:
            critical = "Critical" in archetype
            trace = "Trace" in archetype
            notes.append(
                Single(
                    beat=round(data[EngineArchetypeDataName.Beat], 6),
                    critical=critical,
                    lane=data.get("lane", 0),
                    size=data.get("size", 1),
                    trace=trace,
                    direction=(
                        directions[data["direction"]] if data.get("direction") else None
                    ),
                    timeScaleGroup=0,
                )
            )

    if not has_bpm:
        notes.insert(0, Bpm(beat=round(0, 6), bpm=160.0))
    return Score(metadata=metadata, notes=notes)
