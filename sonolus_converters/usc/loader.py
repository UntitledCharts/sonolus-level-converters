import json
from typing import TextIO
from ..notes.score import Score
from ..notes.metadata import MetaData
from ..notes.bpm import Bpm
from ..notes.timescale import TimeScaleGroup, TimeScalePoint
from ..notes.single import Single
from ..notes.slide import Slide, SlideStartPoint, SlideRelayPoint, SlideEndPoint
from ..notes.guide import Guide, GuidePoint


def load(fp: TextIO) -> Score:
    usc = json.load(fp)
    metadata = MetaData(
        title="",
        artist="",
        designer="",
        waveoffset=usc["usc"]["offset"],
        requests=["ticks_per_beat 480"],
    )

    notelist = []
    has_bpm = False
    for obj in usc["usc"]["objects"]:
        type = obj["type"]

        if type == "bpm":
            notelist.append(Bpm(beat=round(obj["beat"], 6), bpm=obj["bpm"]))
            has_bpm = True

        elif type == "timeScaleGroup":
            group = TimeScaleGroup()
            for timescale in obj["changes"]:
                group.append(
                    TimeScalePoint(
                        beat=round(timescale["beat"], 6),
                        timeScale=timescale["timeScale"],
                    )
                )
            notelist.append(group)

        elif type in ["single", "damage"]:
            if "direction" in obj and type == "single":
                notelist.append(
                    Single(
                        beat=round(obj["beat"], 6),
                        critical=obj["critical"],
                        lane=obj["lane"],
                        size=obj["size"],
                        timeScaleGroup=obj["timeScaleGroup"],
                        trace=obj["trace"],
                        direction=obj["direction"],
                        type="single",
                    )
                )
            else:
                notelist.append(
                    Single(
                        beat=round(obj["beat"], 6),
                        lane=obj["lane"],
                        size=obj["size"],
                        timeScaleGroup=obj["timeScaleGroup"],
                        type=type,
                    )
                )

        elif type == "slide":
            slide = Slide(critical=obj["critical"])
            for point in obj["connections"]:
                if point["type"] == "start":
                    slide.append(
                        SlideStartPoint(
                            beat=round(point["beat"], 6),
                            critical=point["critical"],
                            ease=point["ease"],
                            judgeType=point["judgeType"],
                            lane=point["lane"],
                            size=point["size"],
                            timeScaleGroup=point["timeScaleGroup"],
                        )
                    )
                elif point["type"] in ("tick", "attach"):
                    if "critical" in point:
                        slide.append(
                            SlideRelayPoint(
                                beat=round(point["beat"], 6),
                                ease=point["ease"],
                                lane=point["lane"],
                                size=point["size"],
                                timeScaleGroup=point["timeScaleGroup"],
                                type=point["type"],
                                critical=point["critical"],
                            )
                        )
                    else:
                        slide.append(
                            SlideRelayPoint(
                                beat=round(point["beat"], 6),
                                ease=point["ease"],
                                lane=point["lane"],
                                size=point["size"],
                                timeScaleGroup=point["timeScaleGroup"],
                                type=point["type"],
                            )
                        )
                elif point["type"] == "end":
                    if "direction" in point:
                        slide.append(
                            SlideEndPoint(
                                beat=round(point["beat"], 6),
                                critical=point["critical"],
                                judgeType=point["judgeType"],
                                lane=point["lane"],
                                size=point["size"],
                                timeScaleGroup=point["timeScaleGroup"],
                                direction=point["direction"],
                            )
                        )
                    else:
                        slide.append(
                            SlideEndPoint(
                                beat=round(point["beat"], 6),
                                critical=point["critical"],
                                judgeType=point["judgeType"],
                                lane=point["lane"],
                                size=point["size"],
                                timeScaleGroup=point["timeScaleGroup"],
                            )
                        )
            notelist.append(slide)

        elif type == "guide":
            guide = Guide(color=obj["color"], fade=obj["fade"])
            for point in obj["midpoints"]:
                guide.append(
                    GuidePoint(
                        beat=round(point["beat"], 6),
                        ease=point["ease"],
                        lane=point["lane"],
                        size=point["size"],
                        timeScaleGroup=point["timeScaleGroup"],
                    )
                )
            notelist.append(guide)

    if not has_bpm:
        notelist.insert(0, Bpm(beat=round(0, 6), bpm=160.0))

    return Score(metadata=metadata, notes=notelist)
