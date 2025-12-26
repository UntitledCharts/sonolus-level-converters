from __future__ import annotations


import json
import gzip
from itertools import pairwise
from math import floor
from pathlib import Path
import io
from typing import Union, IO, NoReturn

from ...notes import (
    Bpm,
    TimeScaleGroup,
    TimeScalePoint,
    Single,
    Skill,
    FeverChance,
    FeverStart,
    Slide,
    Guide,
    SlideStartPoint,
    SlideEndPoint,
    SlideRelayPoint,
)
from ...notes.score import Score

from ...utils import SinglePrecisionFloatEncoder

EPSILON = 1e-6


def assert_never(arg: NoReturn) -> NoReturn:
    raise AssertionError("Expected code to be unreachable")


class Entity:
    def __init__(self, archetype: str, data: dict[str, int | float | Entity]):
        self.archetype = archetype
        self.data = data
        self.name = str(id(self))

    def export(self) -> dict:
        return {
            "name": self.name,
            "archetype": self.archetype,
            "data": [
                (
                    {"name": k, "value": v}
                    if not isinstance(v, Entity)
                    else {"name": k, "ref": v.name}
                )
                for k, v in self.data.items()
            ],
        }

    def __getitem__(self, item):
        return self.data[item]

    def __setitem__(self, key, value):
        self.data[key] = value


DIRECTIONS = {
    "left": 1,
    "up": 0,
    "right": 2,
}

CONNECTOR_EASES = {
    "outin": 5,
    "out": 3,
    "linear": 1,
    "in": 2,
    "inout": 4,
}

GUIDE_COLORS = {
    "neutral": 101,
    "red": 102,
    "green": 103,
    "blue": 104,
    "yellow": 105,
    "purple": 106,
    "cyan": 107,
    "black": 108,
}


def export(
    path: Union[str, Path, bytes, io.BytesIO, IO[bytes]],
    score: Score,
    as_compressed: bool = True,
    smooth_guide_fade: bool = False,
    use_guide_layer: bool = False,
):
    entities: list[Entity] = [
        Entity("Initialization", {}),
    ]

    bpm_changes: list[Bpm] = []
    timescale_groups: list[TimeScaleGroup] = []
    single_notes: list[Single] = []
    events: list[Skill, FeverChance, FeverStart] = []
    slide_notes: list[Slide] = []
    guide_notes: list[Guide] = []

    timescale_group_entities: list[Entity] = []
    sim_line_eligible_notes: list[Entity] = []

    for entry in score.notes:
        match entry:
            case Bpm():
                bpm_changes.append(entry)
            case TimeScaleGroup():
                timescale_groups.append(entry)
            case Single():
                single_notes.append(entry)
            case Slide():
                slide_notes.append(entry)
            case Guide():
                guide_notes.append(entry)
            case Skill():
                events.append(entry)
            case FeverChance():
                events.append(entry)
            case FeverStart():
                events.append(entry)
            case _:
                assert_never(entry)

    if len(timescale_groups) == 0:
        timescale_groups.append(TimeScaleGroup(changes=[TimeScalePoint(0, 1)]))
    if len(bpm_changes) == 0:
        bpm_changes.append(Bpm(0, 160))

    for bpm in bpm_changes:
        entities.append(
            Entity(
                "#BPM_CHANGE",
                {
                    "#BEAT": bpm.beat,
                    "#BPM": bpm.bpm,
                },
            )
        )
    for group in timescale_groups:
        group_entity = Entity("#TIMESCALE_GROUP", {})
        entities.append(group_entity)
        timescale_group_entities.append(group_entity)
        last_entity = None
        for change in sorted(group.changes, key=lambda c: c.beat):
            new_entity = Entity(
                "#TIMESCALE_CHANGE",
                {
                    "#BEAT": change.beat,
                    "#TIMESCALE": change.timeScale,
                    "#TIMESCALE_SKIP": 0,
                    "#TIMESCALE_GROUP": group_entity,
                    "#TIMESCALE_EASE": 0,
                },
            )
            if last_entity is None:
                group_entity["first"] = new_entity
            else:
                last_entity["next"] = new_entity
            last_entity = new_entity
            entities.append(new_entity)

    for event in events:
        event_archetypes = {
            "skill": "Skill",
            "feverStart": "FeverStart",
            "feverChance": "FeverChance",
        }
        name = event_archetypes[event.type]
        entity = Entity(
            name,
            {
                "#BEAT": event.beat,
            },
        )
        entities.append(entity)

    for note in single_notes:
        name_parts = []
        if note.fake:
            name_parts.append("Fake")
        if note.type == "damage":
            name_parts.append("Damage")
        else:
            if note.critical:
                name_parts.append("Critical")
            else:
                name_parts.append("Normal")
            if note.direction is None:
                if note.trace:
                    name_parts.append("Trace")
                else:
                    name_parts.append("Tap")
            else:
                if note.trace:
                    name_parts.append("TraceFlick")
                else:
                    name_parts.append("Flick")
        name_parts.append("Note")
        name = "".join(name_parts)
        entity = Entity(
            name,
            {
                "#BEAT": note.beat,
                "#TIMESCALE_GROUP": timescale_group_entities[
                    int(note.timeScaleGroup or 0)
                ],
                "lane": note.lane,
                "size": note.size,
                "direction": DIRECTIONS[getattr(note, "direction", "up") or "up"],
                "isAttached": 0,
                "connectorEase": 1,
                "isSeparator": 0,
                "segmentKind": 2 if note.critical else 1,
                "segmentAlpha": 1,
            },
        )
        entities.append(entity)
        if note.type != "damage":
            sim_line_eligible_notes.append(entity)

    for slide in slide_notes:
        prev_joint_entity: Entity | None = None
        prev_note_entity: Entity | None = None
        head_note_entity: Entity | None = None
        queued_attach_notes: list[Entity] = []
        connectors: list[Entity] = []
        connections = sorted(slide.connections, key=lambda n: n.beat)
        next_hidden_tick_beat = floor(connections[0].beat * 2 + 1) / 2
        for note in connections:
            is_sim_line_eligible = False
            is_attached = False
            name_parts = []
            if slide.fake:
                name_parts.append("Fake")
            match note:
                case SlideStartPoint():
                    if note.judgeType == "none":
                        name_parts.append("Anchor")
                    else:
                        if note.critical:
                            name_parts.append("Critical")
                        else:
                            name_parts.append("Normal")
                        name_parts.append("Head")
                        if note.judgeType == "trace":
                            name_parts.append("Trace")
                        elif note.judgeType == "normal":
                            name_parts.append("Tap")
                        else:
                            assert_never(note.judgeType)
                        is_sim_line_eligible = True
                case SlideEndPoint():
                    if note.judgeType == "none":
                        name_parts.append("Anchor")
                    else:
                        if note.critical:
                            name_parts.append("Critical")
                        else:
                            name_parts.append("Normal")
                        name_parts.append("Tail")
                        if note.direction is None:
                            if note.judgeType == "trace":
                                name_parts.append("Trace")
                            elif note.judgeType == "normal":
                                name_parts.append("Release")
                            else:
                                assert_never(note.judgeType)
                        else:
                            if note.judgeType == "trace":
                                name_parts.append("TraceFlick")
                            elif note.judgeType == "normal":
                                name_parts.append("Flick")
                            else:
                                assert_never(note.judgeType)
                        is_sim_line_eligible = True
                case SlideRelayPoint():
                    if note.type == "tick":
                        if note.critical is not None:
                            if note.critical:
                                name_parts.append("Critical")
                            else:
                                name_parts.append("Normal")
                            name_parts.append("Tick")
                        else:
                            name_parts.append("Anchor")
                    elif note.type == "attach":
                        is_attached = True
                        if note.critical is not None:
                            if note.critical:
                                name_parts.append("Critical")
                            else:
                                name_parts.append("Normal")
                            name_parts.append("Tick")
                        else:
                            name_parts = ["TransientHiddenTick"]
                    else:
                        assert_never(note.type)
                case _:
                    assert_never(note)
            name_parts.append("Note")
            name = "".join(name_parts)
            entity = Entity(
                name,
                {
                    "#BEAT": note.beat,
                    "#TIMESCALE_GROUP": timescale_group_entities[
                        int(note.timeScaleGroup or 0)
                    ],
                    "lane": note.lane,
                    "size": note.size,
                    "direction": DIRECTIONS[getattr(note, "direction", "up") or "up"],
                    "isAttached": 1 if is_attached else 0,
                    "connectorEase": CONNECTOR_EASES[
                        getattr(note, "ease", "linear") or "linear"
                    ],
                    "isSeparator": 0,
                    "segmentKind": 2 if slide.critical else 1,
                    "segmentAlpha": 1,
                    # Slide Notes: Layer 0
                    "segmentLayer": 0,
                },
            )
            entities.append(entity)
            if is_sim_line_eligible:
                sim_line_eligible_notes.append(entity)
            if head_note_entity is None:
                head_note_entity = entity
            entity["activeHead"] = head_note_entity
            if is_attached:
                queued_attach_notes.append(entity)
            else:
                if prev_joint_entity is None:
                    assert not queued_attach_notes
                else:
                    for attach in queued_attach_notes:
                        attach["attachHead"] = prev_joint_entity
                        attach["attachTail"] = entity
                    queued_attach_notes.clear()
                    while next_hidden_tick_beat + EPSILON < entity["#BEAT"]:
                        hidden_tick = Entity(
                            "TransientHiddenTickNote",
                            {
                                "#BEAT": round(next_hidden_tick_beat, 9),
                                "#TIMESCALE_GROUP": timescale_group_entities[0],
                                "lane": entity["lane"],
                                "size": entity["size"],
                                "direction": 0,
                                "isAttached": 1,
                                "connectorEase": 1,
                                "isSeparator": 0,
                                "segmentKind": 1,
                                "segmentAlpha": 0,
                                "activeHead": head_note_entity,
                                "attachHead": prev_joint_entity,
                                "attachTail": entity,
                            },
                        )
                        entities.append(hidden_tick)
                        next_hidden_tick_beat += 0.5
                    connector_entity = Entity(
                        "Connector",
                        {
                            "head": prev_joint_entity,
                            "tail": entity,
                        },
                    )
                    entities.append(connector_entity)
                    connectors.append(connector_entity)
                prev_joint_entity = entity
            if prev_note_entity is not None:
                prev_note_entity["next"] = entity
            prev_note_entity = entity
        assert not queued_attach_notes
        assert head_note_entity is not None
        assert prev_joint_entity is not None
        for connector_entity in connectors:
            connector_entity["segmentHead"] = head_note_entity
            connector_entity["segmentTail"] = prev_joint_entity
            connector_entity["activeHead"] = head_note_entity
            connector_entity["activeTail"] = prev_joint_entity

    for guide in guide_notes:
        connections = sorted(guide.midpoints, key=lambda n: n.beat)
        prev_note_entity: Entity | None = None
        head_note_entity: Entity | None = None
        connectors = []

        step_size = max(1, len(connections) - 1)
        step_idx = 0

        for note in connections:
            segment_alpha = 1
            is_separator = 0

            if smooth_guide_fade:
                is_separator = 1
                if guide.fade == "out":
                    segment_alpha = 1 - 0.8 * (step_idx / step_size)
                elif guide.fade == "in":
                    segment_alpha = 1 - 0.8 * ((step_size - step_idx) / step_size)

            entity = Entity(
                "AnchorNote",
                {
                    "#BEAT": note.beat,
                    "#TIMESCALE_GROUP": timescale_group_entities[
                        int(note.timeScaleGroup or 0)
                    ],
                    "lane": note.lane,
                    "size": note.size,
                    "direction": 0,
                    "isAttached": 0,
                    "connectorEase": CONNECTOR_EASES[note.ease],
                    "isSeparator": is_separator,
                    "segmentKind": GUIDE_COLORS[guide.color],
                    "segmentAlpha": segment_alpha,
                    "segmentLayer": 1 if use_guide_layer else 0,
                },
            )
            entities.append(entity)
            if head_note_entity is None:
                head_note_entity = entity
            if prev_note_entity is not None:
                connector_entity = Entity(
                    "Connector",
                    {
                        "head": prev_note_entity,
                        "tail": entity,
                    },
                )
                entities.append(connector_entity)
                connectors.append(connector_entity)
                prev_note_entity["next"] = entity
            prev_note_entity = entity

            step_idx += 1

        assert head_note_entity is not None
        assert prev_note_entity is not None
        for connector_entity in connectors:
            connector_entity["segmentHead"] = head_note_entity
            connector_entity["segmentTail"] = prev_note_entity
            connector_entity["activeHead"] = head_note_entity
            connector_entity["activeTail"] = prev_note_entity

        if not smooth_guide_fade:
            match guide.fade:
                case "in":
                    head_note_entity["segmentAlpha"] = 0
                case "out":
                    prev_note_entity["segmentAlpha"] = 0
                case "none":
                    pass
                case _:
                    assert_never(guide.fade)

    groups = []
    last_group = []
    for note_entity in sorted(
        sim_line_eligible_notes, key=lambda e: (e["#BEAT"], e["lane"])
    ):
        if not last_group or abs(note_entity["#BEAT"] - last_group[0]["#BEAT"]) < 1e-2:
            last_group.append(note_entity)
        else:
            groups.append(last_group)
            last_group = [note_entity]
    if last_group:
        groups.append(last_group)
    for group in groups:
        for a, b in pairwise(group):
            entity = Entity(
                "SimLine",
                {
                    "left": a,
                    "right": b,
                },
            )
            entities.append(entity)

    leveldata = {
        "bgmOffset": score.metadata.waveoffset,
        "entities": [e.export() for e in entities],
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
