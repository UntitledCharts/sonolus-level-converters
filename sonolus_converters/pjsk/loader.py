import base64
import gzip
import json
import os
from typing import IO, Literal

from ..notes.score import Score
from ..notes.metadata import MetaData
from ..notes.bpm import Bpm
from ..notes.timescale import TimeScaleGroup, TimeScalePoint
from ..notes.single import Single
from ..notes.slide import Slide, SlideStartPoint, SlideRelayPoint, SlideEndPoint
from ..notes.guide import Guide, GuidePoint
from ..notes.volume import Volume


TICKS_PER_BEAT = 480

_DIRECTION_MAP = {0: None, 1: "left", 2: "right"}
_DIRECTION_MAP_REV = {None: 0, "left": 1, "up": 0, "right": 2}

EaseType = Literal["outin", "out", "linear", "in", "inout"]
_EASE_MAP: dict[int, EaseType] = {0: "linear", 1: "out", 2: "in"}
_EASE_MAP_REV = {"linear": 0, "out": 1, "in": 2, "outin": 0, "inout": 0}


def _tick_to_beat(ticks: int) -> float:
    return round(ticks / TICKS_PER_BEAT, 6)


def _convert_lane(lane_start: int, lane_end: int) -> tuple[float, float]:
    lane = (lane_start + lane_end) / 2.0 - 5.5
    size = (lane_end - lane_start + 1) / 2.0
    return lane, size


def _decode(data: bytes) -> dict:
    # base64(gzip(json)) (server format), raw gzip(json), or plain json
    try:
        return json.loads(gzip.decompress(base64.b64decode(data)))
    except Exception:
        pass
    try:
        return json.loads(gzip.decompress(data))
    except Exception:
        pass
    return json.loads(data)


def load_raw(data: os.PathLike | IO[bytes] | bytes | str) -> dict:
    if isinstance(data, (os.PathLike, str)):
        with open(data, "rb") as f:
            raw = f.read()
    elif isinstance(data, bytes):
        raw = data
    else:
        raw = data.read()
    return _decode(raw)


def load(data: os.PathLike | IO[bytes] | bytes | str) -> Score:
    pjsk = load_raw(data)

    metadata = MetaData(
        title="",
        artist="",
        designer="",
        waveoffset=0,
        requests=["ticks_per_beat 480"],
    )

    notes: list = []
    tsg: TimeScaleGroup | None = None

    for event in pjsk.get("MusicScoreEventDataList", []):
        event_type = event["eventType"]
        ticks = event["ticks"]
        beat = _tick_to_beat(ticks)
        value = event["changeValue"]

        if event_type == 0:
            notes.append(Bpm(beat=beat, bpm=float(value)))
        elif event_type == 1:
            if tsg is None:
                tsg = TimeScaleGroup()
                notes.append(tsg)
            tsg.append(TimeScalePoint(beat=beat, timeScale=float(value)))
        elif event_type == 2:
            notes.append(Volume(beat=beat, volume=float(value)))

    if not any(isinstance(n, Bpm) for n in notes):
        notes.insert(0, Bpm(beat=0.0, bpm=120.0))

    note_list = pjsk.get("NoteList", [])
    notes_by_id: dict[int, dict] = {n["id"]: n for n in note_list}
    consumed: set[int] = set()

    chain_heads: list[dict] = []
    for n in note_list:
        if n.get("IsConnectedFirst", False) and n["nextConnectionId"] != -1:
            chain_heads.append(n)

    for head in chain_heads:
        chain: list[dict] = [head]
        consumed.add(head["id"])
        cur = head
        while cur["nextConnectionId"] != -1:
            next_id = cur["nextConnectionId"]
            if next_id not in notes_by_id:
                break
            cur = notes_by_id[next_id]
            chain.append(cur)
            consumed.add(cur["id"])

        if len(chain) < 2:
            continue

        is_guide = head["category"] in (9, 10, 11)

        if is_guide:
            _build_guide(chain, notes)
        else:
            _build_slide(chain, notes)

    for n in note_list:
        if n["id"] in consumed:
            continue
        if not n.get("IsSingle", True):
            continue
        _build_single(n, notes)

    score = Score(metadata=metadata, notes=notes)
    score.sort_by_beat()
    return score


def _build_single(n: dict, notes: list) -> None:
    category = n["category"]
    note_type = n["type"]
    ticks = n["ticks"]
    beat = _tick_to_beat(ticks)
    lane, size = _convert_lane(n["laneStart"], n["laneEnd"])
    critical = note_type == 1
    direction_val = n.get("direction", 0)
    speed_ratio = n.get("speedRatio", 1.0)

    if category == 14:
        return

    if category == 0:
        notes.append(
            Single(
                beat=beat,
                critical=critical,
                lane=lane,
                size=size,
                timeScaleGroup=0,
                speedRatio=speed_ratio,
                trace=False,
                direction=None,
            )
        )
    elif category == 3:
        direction = _DIRECTION_MAP.get(direction_val)
        if direction is None:
            direction = "up"
        notes.append(
            Single(
                beat=beat,
                critical=critical,
                lane=lane,
                size=size,
                timeScaleGroup=0,
                speedRatio=speed_ratio,
                trace=False,
                direction=direction,
            )
        )
    elif category in (4, 5):
        notes.append(
            Single(
                beat=beat,
                critical=critical,
                lane=lane,
                size=size,
                timeScaleGroup=0,
                speedRatio=speed_ratio,
                trace=True,
                direction=None,
            )
        )
    elif category == 8:
        direction = _DIRECTION_MAP.get(direction_val)
        if direction is None:
            direction = "up"
        notes.append(
            Single(
                beat=beat,
                critical=critical,
                lane=lane,
                size=size,
                timeScaleGroup=0,
                speedRatio=speed_ratio,
                trace=True,
                direction=direction,
            )
        )


def _build_slide(chain: list[dict], notes: list) -> None:
    head = chain[0]
    critical = head["type"] == 1
    connections: list = []

    for i, n in enumerate(chain):
        beat = _tick_to_beat(n["ticks"])
        lane, size = _convert_lane(n["laneStart"], n["laneEnd"])
        ease = _EASE_MAP.get(n.get("noteLineType", 0), "linear")
        category = n["category"]
        note_type = n["type"]
        speed_ratio = n.get("speedRatio", 1.0)

        if i == 0:
            if category in (5, 7):
                judge_type = "none"
            elif category in (4, 6):
                judge_type = "trace"
            else:
                judge_type = "normal"

            connections.append(
                SlideStartPoint(
                    beat=beat,
                    critical=note_type == 1,
                    ease=ease,
                    judgeType=judge_type,
                    lane=lane,
                    size=size,
                    timeScaleGroup=0,
                    speedRatio=speed_ratio,
                )
            )
        elif i == len(chain) - 1:
            direction_val = n.get("direction", 0)
            direction = _DIRECTION_MAP.get(direction_val)

            if category == 5:
                judge_type = "none"
            elif category in (4, 8):
                judge_type = "trace"
            else:
                judge_type = "normal"

            if category in (3, 8) and direction is None:
                direction = "up"

            connections.append(
                SlideEndPoint(
                    beat=beat,
                    critical=note_type == 1,
                    judgeType=judge_type,
                    lane=lane,
                    size=size,
                    timeScaleGroup=0,
                    speedRatio=speed_ratio,
                    direction=direction,
                )
            )
        else:
            if category == 13:
                relay_critical = None
            else:
                relay_critical = note_type == 1

            # Normal (category != 13, not skip): changes shape + adds combo (tick + critical)
            # Hidden (category 13): changes shape, no combo (tick + critical=None)
            # Skip (isSkip=true): no shape change, adds combo (attach + critical)
            is_skip = n.get("isSkip", False)

            connections.append(
                SlideRelayPoint(
                    beat=beat,
                    ease=ease,
                    lane=lane,
                    size=size,
                    timeScaleGroup=0,
                    type="attach" if is_skip else "tick",
                    critical=relay_critical,
                    speedRatio=speed_ratio,
                )
            )

    slide = Slide(critical=critical, connections=connections)
    slide.sort()
    notes.append(slide)


def _build_guide(chain: list[dict], notes: list) -> None:
    head = chain[0]
    critical = head["type"] == 1
    color = "yellow" if critical else "green"

    midpoints: list[GuidePoint] = []
    for n in chain:
        beat = _tick_to_beat(n["ticks"])
        lane, size = _convert_lane(n["laneStart"], n["laneEnd"])
        ease = _EASE_MAP.get(n.get("noteLineType", 0), "linear")

        midpoints.append(
            GuidePoint(
                beat=beat,
                ease=ease,
                lane=lane,
                size=size,
                timeScaleGroup=0,
                speedRatio=n.get("speedRatio", 1.0),
            )
        )

    guide = Guide(color=color, fade="none", midpoints=midpoints)
    notes.append(guide)
