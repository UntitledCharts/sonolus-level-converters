import json
from typing import TextIO, Literal

from ...notes.score import Score
from ...notes.metadata import MetaData
from ...notes.bpm import Bpm
from ...notes.timescale import TimeScaleGroup, TimeScalePoint
from ...notes.single import Single
from ...notes.slide import Slide, SlideStartPoint, SlideRelayPoint, SlideEndPoint
from ...notes.guide import Guide, GuidePoint

from ...archetypes import EngineArchetypeName, EngineArchetypeDataName


def load(fp: TextIO) -> Score:
    """Load a pjsekai LevelData file and convert it to a Score object."""
    leveldata = json.load(fp)

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

    def reverse_single_archetype(archetype: str):
        critical = False
        trace = False

        if "Critical" in archetype:
            critical = True

        if "Trace" in archetype:
            trace = True

        return critical, trace

    def reverse_slide_archetype(archetype: str):
        ignored = False  # won't add combo
        hidden = False  # shown/not shown
        critical = False
        trace = False
        attached = False

        active = False  # guide?

        type: Literal["tick", "connector", "end", "start"]
        if "SlideEnd" in archetype:
            type = "end"
        elif "SlideStart" in archetype:
            type = "start"
        elif "SlideTick" in archetype:
            type = "tick"
        elif "SlideConnector" in archetype:
            type = "connector"

        if "Critical" in archetype:
            critical = True
        if "Trace" in archetype:
            trace = True
        if "Attached" in archetype:
            attached = True

        if "Active" in archetype:
            active = True

        if "Ignored" in archetype:
            ignored = True

        if "Hidden" in archetype:
            hidden = True

        return ignored, hidden, critical, trace, attached, active, type

    has_bpm = False
    for entity in leveldata.get("entities", []):
        archetype = entity.get("archetype")
        data = {d["name"]: d.get("value", d.get("ref")) for d in entity.get("data", [])}

        if archetype == "SimLine":
            continue  # disregard, this is just the generated "white line" to show notes that come at the same time

        # BPM
        elif archetype == EngineArchetypeName.BpmChange:
            notes.append(
                Bpm(
                    beat=round(data[EngineArchetypeDataName.Beat], 6),
                    bpm=data[EngineArchetypeDataName.Bpm],
                )
            )
            has_bpm = True

        # TimeScale
        elif archetype == EngineArchetypeName.TimeScaleChange:
            group = TimeScaleGroup()
            group.append(
                TimeScalePoint(
                    beat=round(data[EngineArchetypeDataName.Beat], 6),
                    timeScale=data[EngineArchetypeDataName.TimeScale],
                )
            )
            notes.append(group)

        # Single / Tap / Flick / Trace Notes
        elif "Note" in archetype and "Slide" not in archetype:
            critical, trace = reverse_single_archetype(archetype)
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

        # Slide and guide notes
        elif "Slide" in archetype:
            ignored, hidden, critical, trace, attached, active, type = (
                reverse_slide_archetype(archetype)
            )
            # raise NotImplementedError("oop")
            if active:
                slide = Slide(critical=critical)
                connections = data.get("connections", [])
                for point in connections:
                    pt_type = point.get("type")
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
                                judgeType=point.get("judgeType")
                            )
                        )
                    elif pt_type in ("tick", "attach"):
                        slide.append(
                            SlideRelayPoint(
                                **common_args,
                                type=pt_type,
                                critical=point.get("critical", False),
                                ease=point.get("ease")
                            )
                        )
                    elif pt_type == "end":
                        slide.append(
                            SlideEndPoint(
                                **common_args,
                                critical=point.get("critical", False),
                                judgeType=point.get("judgeType"),
                                direction=point.get("direction")
                            )
                        )
                notes.append(slide)

            # Guide notes
            else:
                guide = Guide(color=data.get("color"), fade=data.get("fade"))
                for point in data.get("midpoints", []):
                    guide.append(
                        GuidePoint(
                            beat=round(point[EngineArchetypeDataName.Beat], 6),
                            ease=point.get("ease"),
                            lane=point.get("lane", 0),
                            size=point.get("size", 1),
                            timeScaleGroup=0,
                        )
                    )
                notes.append(guide)

    if not has_bpm:
        notes.insert(0, Bpm(beat=round(0, 6), bpm=160.0))

    return Score(metadata=metadata, notes=notes)
