import json
import gzip
from dataclasses import dataclass, asdict
from pathlib import Path
import io
from typing import Dict, List, Union, Optional, Callable, Literal, IO
import math

import base36

from ...notes.score import Score
from ...notes.bpm import Bpm
from ...notes.timescale import TimeScaleGroup
from ...notes.single import Single
from ...notes.slide import Slide, SlideRelayPoint
from ...notes.guide import Guide

from ...notes.engine.archetypes import EngineArchetypeName, EngineArchetypeDataName
from ...notes.engine.level import LevelData, LevelDataEntity

from ...utils import SinglePrecisionFloatEncoder

EPSILON = 1e-6


@dataclass
class Intermediate:
    archetype: str
    data: Dict[str, Union[float, "Intermediate", bool, str]]
    sim: bool
    timeScaleGroup: Optional[int] = None
    ref: Optional[str] = None


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
    """
    Automatically replaces extended eases.
    """
    score.replace_extended_ease()  # XXX: they don't support inout or outin? According to their commits on usctool-custom

    # XXX: support isdummy/fake notes on export

    if not any(isinstance(note, Bpm) for note in score.notes):
        score.notes.insert(0, Bpm(beat=round(0, 6), bpm=160.0))
    score.sort_by_beat()

    entities: List[LevelDataEntity] = []
    intermediate_entities: Dict[int, LevelDataEntity] = {}  # intermediate.ref -> entity
    time_to_intermediates: Dict[Union[float, int], List[Intermediate]] = (
        {}
    )  # beat -> list of intermediate
    ref_counter = 0

    def get_ref(intermediate: Intermediate) -> str:
        if intermediate.ref is not None:
            return intermediate.ref
        nonlocal ref_counter
        intermediate.ref = base36.dumps(ref_counter)
        ref_counter += 1
        return intermediate.ref

    def append(intermediate: Intermediate):
        # Ensure intermediate has a unique ref
        ref = get_ref(intermediate)

        entity = LevelDataEntity(archetype=intermediate.archetype, data=[], name=ref)
        entities.append(entity)
        intermediate_entities[ref] = entity

        # Should it generate a simline?
        if intermediate.sim:
            beat = intermediate.data.get(EngineArchetypeDataName.Beat)
            if type(beat) not in (int, float):
                raise ValueError("Unexpected beat")

            time_to_intermediates.setdefault(beat, []).append(intermediate)

        for name, value in intermediate.data.items():
            if isinstance(value, (int, float)):
                entity.data.append({"name": name, "value": value})
            elif isinstance(value, bool):
                entity.data.append({"name": name, "value": 1 if value else 0})
            elif isinstance(value, str):
                entity.data.append({"name": name, "ref": value})
            else:  # another Intermediate
                entity.data.append({"name": name, "ref": get_ref(value)})

        if intermediate.timeScaleGroup is not None:
            entity.data.append(
                {"name": "timeScaleGroup", "ref": f"tsg:{intermediate.timeScaleGroup}"}
            )

    # Initialization entities
    append(Intermediate("Initialization", {}, False, None))
    append(Intermediate("InputManager", {}, False, None))
    append(Intermediate("Stage", {}, False, None))

    # TimeScaleGroups
    ts_group_index = -1
    ts_group_entities: List[LevelDataEntity] = []
    ts_change_entities: List[LevelDataEntity] = []

    ts_groups = [n for n in score.notes if isinstance(n, TimeScaleGroup)]
    for ts_group in ts_groups:
        ts_group_index += 1
        changes = sorted(ts_group.changes, key=lambda c: c.beat)
        for idx, change in enumerate(changes):
            if idx + 1 < len(changes):
                next_ref = {"name": "next", "ref": f"tsc:{ts_group_index}:{idx + 1}"}
            else:
                next_ref = {"name": "next", "value": -1}
            ts_change_entities.append(
                LevelDataEntity(
                    archetype="TimeScaleChange",
                    data=[
                        {"name": EngineArchetypeDataName.Beat, "value": change.beat},
                        {
                            "name": "timeScale",
                            "value": float(
                                0.000001 if change.timeScale == 0 else change.timeScale
                            ),
                        },
                        next_ref,
                    ],
                    name=f"tsc:{ts_group_index}:{idx}",
                )
            )
        next_group = (
            {"name": "next", "value": -1}
            if ts_group_index == len(ts_groups) - 1
            else {"name": "next", "ref": f"tsg:{ts_group_index + 1}"}
        )
        ts_group_entities.append(
            LevelDataEntity(
                archetype="TimeScaleGroup",
                data=[
                    {"name": "first", "ref": f"tsc:{ts_group_index}:0"},
                    {"name": "length", "value": len(changes)},
                    next_group,
                ],
                name=f"tsg:{ts_group_index}",
            )
        )

    if ts_group_index == -1:
        # no timescale groups
        entities.append(
            LevelDataEntity(
                archetype="TimeScaleGroup",
                data=[
                    {"name": "first", "ref": "tsc:0:0"},
                    {"name": "length", "value": 0},
                ],
                name="tsg:0",
            )
        )
        entities.append(
            LevelDataEntity(
                archetype="TimeScaleChange",
                data=[
                    {"name": EngineArchetypeDataName.Beat, "value": 0.0},
                    {"name": "timeScale", "value": 1.0},
                    {"name": "timeScaleGroup", "ref": "tsg:0"},
                ],
                name="tsc:0:0",
            )
        )
    else:
        entities.extend(ts_group_entities)
        entities.extend(ts_change_entities)

    directions = {"left": -1, "up": 0, "right": 1}
    eases = {"outin": -2, "out": -1, "linear": 0, "in": 1, "inout": 2}
    slide_starts = {"tap": 0, "trace": 1, "none": 2}
    colors = {
        "neutral": 0,
        "red": 1,
        "green": 2,
        "blue": 3,
        "yellow": 4,
        "purple": 5,
        "cyan": 6,
        "black": 7,
    }
    fades = {
        "in": 2,
        "out": 0,
        "none": 1,
    }

    def handle_bpm(obj: Bpm):
        return Intermediate(
            archetype=EngineArchetypeName.BpmChange,
            data={
                EngineArchetypeDataName.Beat: obj.beat,
                EngineArchetypeDataName.Bpm: obj.bpm,
            },
            sim=False,
            timeScaleGroup=None,
        )

    def handle_timescale(obj: TimeScaleGroup):
        return None  # handled separately above

    def handle_single(obj: Single):
        if obj.type == "damage":
            inter = Intermediate(
                data={
                    EngineArchetypeDataName.Beat: obj.beat,
                    "lane": obj.lane,
                    "size": obj.size,
                },
                sim=False,
                timeScaleGroup=obj.timeScaleGroup,
            )
        else:
            inter = Intermediate(
                archetype="CriticalTapNote" if obj.critical else "NormalTapNote",
                data={
                    EngineArchetypeDataName.Beat: obj.beat,
                    "lane": obj.lane,
                    "size": obj.size,
                },
                sim=True,
                timeScaleGroup=obj.timeScaleGroup,
            )
            if obj.trace:
                inter.archetype = (
                    "CriticalTraceNote" if obj.critical else "NormalTraceNote"
                )
                if obj.direction:
                    if obj.direction == "none":
                        inter.archetype = "NonDirectionalTraceFlickNote"
                    else:
                        inter.archetype = (
                            "CriticalTraceFlickNote"
                            if obj.critical
                            else "NormalTraceFlickNote"
                        )
                        inter.data["direction"] = directions[obj.direction]
            else:
                if obj.direction and obj.direction != "none":
                    inter.archetype = (
                        "CriticalFlickNote" if obj.critical else "NormalFlickNote"
                    )
                    inter.data["direction"] = directions[obj.direction]
                elif obj.direction == "none":
                    return None
        return inter

    def get_slide_connections(obj: Slide):
        connections = list(obj.connections)
        beats = sorted(c.beat for c in connections)
        min_beat, max_beat = beats[0], beats[-1]
        start = max(
            math.ceil((min_beat - EPSILON) / 0.5) * 0.5,
            math.floor((min_beat + EPSILON) / 0.5 + 1) * 0.5,
        )
        num_steps = int(math.floor((max_beat - start) / 0.5 + EPSILON))

        # Generate beats
        for i in range(num_steps):
            beat = round(start + i * 0.5, 9)  # round to prevent float drift
            if beat + EPSILON >= max_beat:
                break
            connections.append(
                SlideRelayPoint(
                    beat=beat,
                    type="attach",
                    lane=0,
                    size=0,
                    timeScaleGroup=0,
                    ease="linear",
                )
            )
        start_step = next(c for c in connections if c.type == "start")
        end_step = next(c for c in connections if c.type == "end")
        steps = sorted(
            [c for c in connections if c.type in ("tick", "attach")],
            key=lambda x: x.beat,
        )
        if not start_step:
            raise KeyError("Missing start")
        if not end_step:
            raise KeyError("Missing end")
        return [start_step] + steps + [end_step]

    @dataclass
    class ConnectionIntermediate(Intermediate):
        ease: Optional[Literal["outin", "out", "linear", "in", "inout"]] = None
        # XXX: inout is probably best converted as out
        # XXX: outin is probably best converted as in
        # XXX: ideal situation is to put an attach note halfway through and combine ease but pain
        # XXX: the notes here are for loading ChCy and converting to, .sus or .usc

    def handle_slide(obj: Slide):
        cis: List[ConnectionIntermediate] = []
        joints: List[ConnectionIntermediate] = []
        attaches: List[ConnectionIntermediate] = []
        ends: List[ConnectionIntermediate] = []

        connections = get_slide_connections(obj)
        start_type = "tap"

        for i, connection in enumerate(connections):
            if i == 0 and connection.type == "start":
                if connection.judgeType == "none":
                    archetype = "HiddenSlideStartNote"
                    sim = False
                    start_type = "none"
                elif connection.judgeType == "trace":
                    archetype = (
                        "CriticalTraceSlideStartNote"
                        if connection.critical
                        else "NormalTraceSlideStartNote"
                    )
                    sim = True
                    start_type = "trace"
                else:
                    archetype = (
                        "CriticalSlideStartNote"
                        if connection.critical
                        else "NormalSlideStartNote"
                    )
                    sim = True
                    start_type = "tap"
                ci = ConnectionIntermediate(
                    archetype,
                    {
                        EngineArchetypeDataName.Beat: connection.beat,
                        "lane": connection.lane,
                        "size": connection.size,
                    },
                    sim,
                    connection.timeScaleGroup,
                    ease=connection.ease,
                )
                cis.append(ci)
                joints.append(ci)
                continue
            elif i == len(connections) - 1 and connection.type == "end":
                if connection.judgeType == "none":
                    ci = ConnectionIntermediate(
                        "HiddenSlideTickNote",
                        {
                            EngineArchetypeDataName.Beat: connection.beat,
                            "lane": connection.lane,
                            "size": connection.size,
                        },
                        sim=False,
                        timeScaleGroup=connection.timeScaleGroup,
                    )
                else:
                    archetype = (
                        "CriticalTraceSlideEndNote"
                        if connection.critical and connection.judgeType == "trace"
                        else (
                            "NormalTraceSlideEndNote"
                            if connection.judgeType == "trace"
                            else (
                                "CriticalSlideEndNote"
                                if connection.critical
                                else "NormalSlideEndNote"
                            )
                        )
                    )
                    ci = ConnectionIntermediate(
                        archetype,
                        {
                            EngineArchetypeDataName.Beat: connection.beat,
                            "lane": connection.lane,
                            "size": connection.size,
                        },
                        sim=True,
                        timeScaleGroup=connection.timeScaleGroup,
                    )
                    if (
                        hasattr(connection, "direction")
                        and connection.direction != None
                    ):
                        ci.archetype = (
                            "CriticalSlideEndFlickNote"
                            if connection.critical
                            else "NormalSlideEndFlickNote"
                        )
                        ci.data["direction"] = directions[connection.direction]
                cis.append(ci)
                joints.append(ci)
                ends.append(ci)
                continue
            elif connection.type == "tick":
                archetype = "HiddenSlideTickNote"
                if hasattr(connection, "critical") and connection.critical != None:
                    archetype = (
                        "CriticalSlideTickNote"
                        if connection.critical
                        else "NormalSlideTickNote"
                    )

                ci = ConnectionIntermediate(
                    archetype,
                    {
                        EngineArchetypeDataName.Beat: connection.beat,
                        "lane": connection.lane,
                        "size": connection.size,
                    },
                    sim=False,
                    ease=connection.ease,
                    timeScaleGroup=connection.timeScaleGroup,
                )
                cis.append(ci)
                joints.append(ci)
            elif connection.type == "attach":
                archetype = "IgnoredSlideTickNote"
                if hasattr(connection, "critical") and connection.critical != None:
                    archetype = (
                        "CriticalAttachedSlideTickNote"
                        if connection.critical
                        else "NormalAttachedSlideTickNote"
                    )

                ci = ConnectionIntermediate(
                    archetype,
                    {EngineArchetypeDataName.Beat: connection.beat},
                    sim=False,
                )
                ci.ease = connection.ease
                if archetype != "IgnoredSlideTickNote":
                    ci.timeScaleGroup = connection.timeScaleGroup

                cis.append(ci)
                attaches.append(ci)
            else:
                raise KeyError(f"Unexpected slide type {connection.type}")
        connectors: List[ConnectionIntermediate] = []
        start = cis[0]
        for i, joint in enumerate(joints):
            if i == 0:
                continue
            head = joints[i - 1]
            if not hasattr(head, "ease") or head.ease == None:
                raise ValueError("Unexpected missing ease")
            archetype = (
                "CriticalSlideConnector" if obj.critical else "NormalSlideConnector"
            )
            connectors.append(
                ConnectionIntermediate(
                    archetype,
                    {
                        "start": start,
                        "end": ends[0],
                        "head": head,
                        "tail": joint,
                        "ease": eases[head.ease],
                        "startType": slide_starts[start_type],
                    },
                    sim=False,
                )
            )

        for attach in attaches:
            index = cis.index(attach)
            tail_index = next(
                (i for i, c in enumerate(joints) if cis.index(c) > index), None
            )
            if tail_index is None or tail_index - 1 < 0:
                continue
            attach.data["attach"] = connectors[tail_index - 1]

        for end in ends:
            end.data["slide"] = connectors[-1]
        cis = list(sorted(cis, key=lambda x: x.data[EngineArchetypeDataName.Beat]))
        return cis + connectors

    def handle_guide(obj: Guide):
        intermediates: List[Intermediate] = []
        start = obj.midpoints[0]
        end = obj.midpoints[-1]
        for i, joint in enumerate(obj.midpoints[1:], start=1):
            head = obj.midpoints[i - 1]
            intermediates.append(
                Intermediate(
                    "Guide",
                    {
                        "color": colors[obj.color],
                        "fade": fades[obj.fade],
                        "ease": eases[head.ease],
                        "startLane": start.lane,
                        "startSize": start.size,
                        "startBeat": start.beat,
                        "startTimeScaleGroup": f"tsg:{getattr(start, 'timeScaleGroup', 0)}",
                        "headLane": head.lane,
                        "headSize": head.size,
                        "headBeat": head.beat,
                        "headTimeScaleGroup": f"tsg:{getattr(head, 'timeScaleGroup', 0)}",
                        "tailLane": joint.lane,
                        "tailSize": joint.size,
                        "tailBeat": joint.beat,
                        "tailTimeScaleGroup": f"tsg:{getattr(joint, 'timeScaleGroup', 0)}",
                        "endLane": end.lane,
                        "endSize": end.size,
                        "endBeat": end.beat,
                        "endTimeScaleGroup": f"tsg:{getattr(end, 'timeScaleGroup', 0)}",
                    },
                    sim=False,
                    timeScaleGroup=None,
                )
            )
        return intermediates

    handlers: Dict[str, Callable] = {
        "bpm": handle_bpm,
        "timeScaleGroup": handle_timescale,
        "single": handle_single,
        "slide": handle_slide,
        "guide": handle_guide,
    }

    for note in score.notes:
        handler = handlers.get(note.type)
        if handler is None:
            raise ValueError(f"Unknown note type: {note.type}")
        result = handler(note)
        if isinstance(result, list):
            for item in result:
                if item:
                    append(item)
        elif result:
            append(result)

    # SimLine connections
    for intermediates in time_to_intermediates.values():
        for j in range(1, len(intermediates)):
            append(
                Intermediate(
                    archetype="SimLine",
                    data={"a": intermediates[j - 1], "b": intermediates[j]},
                    sim=False,
                    timeScaleGroup=None,
                )
            )

    entities = [asdict(entity) for entity in entities]
    _remove_none(entities)

    # # Debug: detect duplicate entity names
    # from collections import Counter

    # names = [e.get("name") for e in entities if e.get("name") is not None]
    # dup = [name for name, count in Counter(names).items() if count > 1]
    # if dup:
    #     raise RuntimeError(f"Duplicate entity names found: {dup}")

    leveldata: LevelData = {
        "bgmOffset": score.metadata.waveoffset,
        "entities": entities,
    }

    if isinstance(path, (str, Path)):
        path = Path(path)
        if not as_compressed:
            with path.open("w", encoding="utf-8") as f:
                json.dump(
                    leveldata,
                    f,
                    indent=4,
                    ensure_ascii=False,
                    cls=SinglePrecisionFloatEncoder,
                )
        else:
            with gzip.open(f"{path}", "wb") as f:
                data = json.dumps(
                    leveldata,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    cls=SinglePrecisionFloatEncoder,
                ).encode("utf-8")
                f.write(data)
    elif isinstance(path, io.BytesIO) or (
        hasattr(path, "write") and callable(path.write)
    ):
        if not as_compressed:
            json_text = json.dumps(
                leveldata, indent=4, ensure_ascii=False, cls=SinglePrecisionFloatEncoder
            )
            path.write(json_text.encode("utf-8"))
        else:
            data = json.dumps(
                leveldata,
                ensure_ascii=False,
                separators=(",", ":"),
                cls=SinglePrecisionFloatEncoder,
            ).encode("utf-8")
            with gzip.GzipFile(fileobj=path, mode="wb", mtime=0) as f:
                f.write(data)
        path.seek(0)
