import json, gzip
from dataclasses import dataclass, asdict
from pathlib import Path
import io
from typing import Dict, List, Union, Optional, Literal, IO

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
    data: Dict[str, Union[float, "Intermediate", None]]
    sim: bool
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
    Automatically replaces extended eases and guide colors, deleting fake and damage notes.

    If you want to define your custom color map for replacing, run the .replace_extended_guide_colors with your own map.
    """
    score.replace_extended_ease()
    score.replace_extended_guide_colors()
    score.delete_fake_notes()
    score.delete_damage_notes()
    if not any(isinstance(note, Bpm) for note in score.notes):
        score.notes.insert(0, Bpm(beat=round(0, 6), bpm=160.0))

    entities: List[LevelDataEntity] = []
    intermediate_entities: Dict[int, LevelDataEntity] = {}  # intermediate.ref -> entity
    time_to_intermediates: Dict[Union[float, int], List[Intermediate]] = (
        {}
    )  # beat -> list of intermediate
    ref_counter = 1

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
            if value is None:
                continue
            if isinstance(value, (int, float)):
                entity.data.append({"name": name, "value": value})
            else:
                entity.data.append({"name": name, "ref": get_ref(value)})

    append(Intermediate(archetype="Initialization", data={}, sim=False))
    append(Intermediate(archetype="Stage", data={}, sim=False))

    directions = {
        "left": -1,
        "up": 0,
        "right": 1,
    }

    eases = {
        "out": -1,
        "linear": 0,
        "in": 1,
    }

    @dataclass
    class HiddenSlideRelayPoint:
        beat: float
        type: Literal["hidden"]

    def get_connections(note: Slide, active: bool):
        if not active:
            return note.connections

        connections = note.connections.copy()

        beats = sorted(connection.beat for connection in connections)
        min_beat, max_beat = beats[0], beats[-1]

        # Calculate the start beat (next multiple of 0.5)
        start = max(round(min_beat / 0.5) * 0.5, round((min_beat / 0.5 + 1)) * 0.5)

        beat = start
        while beat < max_beat - EPSILON:
            # round to avoid cumulative float drift
            safe_beat = round(beat, 9)
            connections.append(HiddenSlideRelayPoint(beat=safe_beat, type="hidden"))
            beat += 0.5

        # Sort by beat
        connections.sort(key=lambda x: x.beat)
        return connections

    # Convert Score notes to intermediates
    for note in score.notes:
        if isinstance(note, Bpm):
            append(
                Intermediate(
                    archetype=EngineArchetypeName.BpmChange,
                    data={
                        EngineArchetypeDataName.Beat: note.beat,
                        EngineArchetypeDataName.Bpm: note.bpm,
                    },
                    sim=False,
                )
            )
        elif isinstance(note, TimeScaleGroup):
            for point in note.changes:
                append(
                    Intermediate(
                        archetype=EngineArchetypeName.TimeScaleChange,
                        data={
                            EngineArchetypeDataName.Beat: point.beat,
                            EngineArchetypeDataName.TimeScale: point.timeScale,
                        },
                        sim=False,
                    )
                )
        elif isinstance(note, Single):
            archetype = (
                "CriticalTraceFlickNote"
                if note.direction and note.trace and note.critical
                else (
                    "NormalTraceFlickNote"
                    if note.direction and note.trace
                    else (
                        "CriticalFlickNote"
                        if note.direction and note.critical
                        else (
                            "NormalFlickNote"
                            if note.direction
                            else (
                                "CriticalTraceNote"
                                if note.trace and note.critical
                                else (
                                    "NormalTraceNote"
                                    if note.trace
                                    else (
                                        "CriticalTapNote"
                                        if note.critical
                                        else "NormalTapNote"
                                    )
                                )
                            )
                        )
                    )
                )
            )
            intermediate = Intermediate(
                archetype=archetype,
                data={
                    EngineArchetypeDataName.Beat: note.beat,
                    "lane": note.lane,
                    "size": note.size,
                    "direction": directions[note.direction] if note.direction else None,
                },
                sim=True,
            )
            append(intermediate)
        elif isinstance(note, (Slide, Guide)):
            active = True

            if isinstance(note, Guide):
                active = False
                converted_connections = []
                for point in note.midpoints:
                    sr = SlideRelayPoint(
                        type="tick",
                        beat=point.beat,
                        lane=point.lane,
                        size=point.size,
                        ease=point.ease,
                        timeScaleGroup=0,
                        critical=None,  # usc: ignored
                    )
                    converted_connections.append(sr)

                note = Slide(
                    critical=note.color == "yellow", connections=converted_connections
                )

            @dataclass
            class ConnectionIntermediate(Intermediate):
                ease: Optional[Literal["out", "linear", "in"]] = None

            cis: List[ConnectionIntermediate] = []
            joints: List[ConnectionIntermediate] = []
            attaches: List[ConnectionIntermediate] = []
            ends: List[ConnectionIntermediate] = []

            connections = get_connections(note, active)

            for i, connection in enumerate(connections):
                if i == 0:
                    if connection.type == "start" and connection.judgeType != "none":
                        archetype = (
                            "CriticalSlideTraceNote"
                            if connection.judgeType == "trace" and connection.critical
                            else (
                                "NormalSlideTraceNote"
                                if connection.judgeType == "trace"
                                else (
                                    "CriticalSlideStartNote"
                                    if connection.critical
                                    else "NormalSlideStartNote"
                                )
                            )
                        )
                        ci = ConnectionIntermediate(
                            archetype=archetype,
                            data={
                                EngineArchetypeDataName.Beat: connection.beat,
                                "lane": connection.lane,
                                "size": connection.size,
                            },
                            sim=True,
                            ease=connection.ease,
                        )
                        cis.append(ci)
                        joints.append(ci)
                        continue
                    elif (
                        connection.type == "start" and connection.judgeType == "none"
                    ) or (
                        not active
                        and (connection.type == "tick" and connection.critical == None)
                    ):  # usc: ignore
                        ci = ConnectionIntermediate(
                            archetype="IgnoredSlideTickNote",
                            data={
                                EngineArchetypeDataName.Beat: connection.beat,
                                "lane": connection.lane,
                                "size": connection.size,
                            },
                            sim=False,
                            ease=connection.ease,
                        )
                        cis.append(ci)
                        joints.append(ci)
                        continue
                    else:
                        raise ValueError("Unexpected slide start", note, active)

                if i == len(connections) - 1:
                    if connection.type == "end" and connection.judgeType != "none":
                        if connection.direction:
                            if connection.judgeType == "trace":
                                if connection.critical:
                                    archetype = "CriticalTraceFlickNote"
                                else:
                                    archetype = "NormalTraceFlickNote"
                            else:
                                if connection.critical:
                                    archetype = "CriticalSlideEndFlickNote"
                                else:
                                    archetype = "NormalSlideEndFlickNote"
                        else:
                            if connection.judgeType == "trace":
                                if connection.critical:
                                    archetype = "CriticalSlideEndTraceNote"
                                else:
                                    archetype = "NormalSlideEndTraceNote"
                            else:
                                if connection.critical:
                                    archetype = "CriticalSlideEndNote"
                                else:
                                    archetype = "NormalSlideEndNote"
                        ci = Intermediate(
                            archetype=archetype,
                            data={
                                EngineArchetypeDataName.Beat: connection.beat,
                                "lane": connection.lane,
                                "size": connection.size,
                                "direction": (
                                    directions.get(connection.direction)
                                    if connection.direction
                                    else None
                                ),
                            },
                            sim=True,
                        )
                        cis.append(ci)
                        joints.append(ci)
                        ends.append(ci)
                        continue

                    elif (
                        connection.type == "end" and connection.judgeType == "none"
                    ) or (
                        not active
                        and (connection.type == "tick" and connection.critical == None)
                    ):  # usc: ignore
                        ci = ConnectionIntermediate(
                            archetype="IgnoredSlideTickNote",
                            data={
                                EngineArchetypeDataName.Beat: connection.beat,
                                "lane": connection.lane,
                                "size": connection.size,
                            },
                            sim=False,
                            ease="linear",
                        )
                        cis.append(ci)
                        joints.append(ci)
                        continue
                    else:
                        raise ValueError("Unexpected slide end", note, active)

                if (
                    connection.type == "tick" and connection.critical == None
                ):  # usc: ignore
                    ci = ConnectionIntermediate(
                        archetype="IgnoredSlideTickNote",
                        data={
                            EngineArchetypeDataName.Beat: connection.beat,
                            "lane": connection.lane,
                            "size": connection.size,
                        },
                        sim=False,
                        ease=connection.ease,
                    )
                    cis.append(ci)
                    joints.append(ci)
                elif connection.type == "tick":
                    # connection.judgeType == "trace" doesn't exist
                    # replaced with "if False"
                    # CriticalSlideTraceNote and NormalSlideTraceNote aren't a thing lol
                    # Instead, they are properly loaded from sus/usc as a separate trace note
                    # XXX: loading from exporter, convert these notes into separate trace notes
                    # XXX: replace with a attach tick with same settings
                    ci = ConnectionIntermediate(
                        archetype=(
                            "CriticalSlideTraceNote"
                            if False and connection.critical
                            else (
                                "NormalSlideTraceNote"
                                if False
                                else (
                                    "CriticalSlideTickNote"
                                    if connection.critical
                                    else "NormalSlideTickNote"
                                )
                            )
                        ),
                        data={
                            EngineArchetypeDataName.Beat: connection.beat,
                            "lane": connection.lane,
                            "size": connection.size,
                        },
                        sim=False,
                        ease=connection.ease,
                    )
                    cis.append(ci)
                    joints.append(ci)
                elif connection.type == "hidden":
                    ci = Intermediate(
                        archetype="HiddenSlideTickNote",
                        data={EngineArchetypeDataName.Beat: connection.beat},
                        sim=False,
                    )
                    cis.append(ci)
                    attaches.append(ci)
                elif connection.type == "attach":
                    ci = Intermediate(
                        archetype=(
                            "CriticalAttachedSlideTickNote"
                            if connection.critical
                            else "NormalAttachedSlideTickNote"
                        ),
                        data={EngineArchetypeDataName.Beat: connection.beat},
                        sim=False,
                    )
                    cis.append(ci)
                    attaches.append(ci)
                else:
                    raise ValueError("Unexpected slide tick")

            connectors = []

            start = cis[0]
            end = cis[-1]

            for i, joint in enumerate(joints):
                if i == 0:
                    continue

                head = joints[i - 1]
                if not head.ease:
                    raise ValueError("Unexpected missing ease")

                ci = Intermediate(
                    archetype=(
                        "CriticalActiveSlideConnector"
                        if active and note.critical
                        else (
                            "NormalActiveSlideConnector"
                            if active
                            else (
                                "CriticalSlideConnector"
                                if note.critical
                                else "NormalSlideConnector"
                            )
                        )
                    ),
                    data={
                        "start": start,
                        "end": end,
                        "head": head,
                        "tail": joint,
                        "ease": eases.get(head.ease),
                    },
                    sim=False,
                )
                connectors.append(ci)

            for attach in attaches:
                index = cis.index(attach)
                tail_index = next(
                    (i for i, c in enumerate(joints) if cis.index(c) > index), -1
                )
                attach.data["attach"] = (
                    connectors[tail_index - 1] if tail_index >= 0 else None
                )

            for end in ends:
                end.data["slide"] = connectors[-1]

            # Append all intermediate connections and connectors
            for ci in cis:
                append(ci)

            for connector in connectors:
                append(connector)

    for intermediates in time_to_intermediates.values():
        for i in range(1, len(intermediates)):
            append(
                Intermediate(
                    archetype="SimLine",
                    data={"a": intermediates[i - 1], "b": intermediates[i]},
                    sim=False,
                )
            )

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
