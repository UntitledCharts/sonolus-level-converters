from __future__ import annotations


import json
import gzip
from math import floor
from pathlib import Path
import io
from typing import Union, IO, assert_never

from ...notes import (
    Bpm,
    TimeScaleGroup,
    Single,
    Slide,
    Guide,
    SlideStartPoint,
    SlideEndPoint,
    SlideRelayPoint,
)
from ...notes.score import Score


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
                {"name": k, "value": v}
                if not isinstance(v, Entity)
                else {"name": k, "ref": v.name}
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
):
    entities: list[Entity] = [
        Entity("Initialization", {}),
    ]

    bpm_changes: list[Bpm] = []
    timescale_groups: list[TimeScaleGroup] = []
    single_notes: list[Single] = []
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
            case _:
                assert_never(entry)

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
        last_entity = group_entity
        for change in group.changes:
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
            last_entity["next"] = new_entity
            last_entity = new_entity
            entities.append(new_entity)

    for note in single_notes:
        name_parts = []
        if note.fake:
            name_parts.append("Fake")
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
        sim_line_eligible_notes.append(entity)

    for slide in slide_notes:
        prev_joint: Entity | None = None
        prev_note: Entity | None = None
        head_note: Entity | None = None
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
                                name_parts.append("Tap")
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
                },
            )
            entities.append(entity)
            if is_sim_line_eligible:
                sim_line_eligible_notes.append(entity)
            if head_note is None:
                head_note = entity
            entity["activeHead"] = head_note
            if is_attached:
                queued_attach_notes.append(entity)
            else:
                if prev_joint is None:
                    assert not queued_attach_notes
                else:
                    for attach in queued_attach_notes:
                        attach["attachHead"] = prev_joint
                        attach["attachTail"] = entity
                    queued_attach_notes.clear()
                    while next_hidden_tick_beat <= entity["#BEAT"]:
                        hidden_tick = Entity(
                            "TransientHiddenTickNote",
                            {
                                "#BEAT": next_hidden_tick_beat,
                                "#TIMESCALE_GROUP": 0,
                                "lane": entity["lane"],
                                "size": entity["size"],
                                "direction": 0,
                                "isAttached": 1,
                                "connectorEase": 1,
                                "isSeparator": 0,
                                "segmentKind": 1,
                                "segmentAlpha": 0,
                                "activeHead": head_note,
                                "attachHead": prev_joint,
                                "attachTail": entity,
                            },
                        )
                        entities.append(hidden_tick)
                        next_hidden_tick_beat += 0.5
                    connector_entity = Entity(
                        "Connector",
                        {
                            "head": prev_joint,
                            "tail": entity,
                        },
                    )
                    entities.append(connector_entity)
                    connectors.append(connector_entity)
                prev_joint = entity
            if prev_note is not None:
                prev_note["next"] = entity
            prev_note = entity
        assert not queued_attach_notes
        assert head_note is not None
        assert prev_joint is not None
        for connector in connectors:
            connector["segmentHead"] = head_note
            connector["segmentTail"] = prev_joint
            connector["activeHead"] = head_note
            connector["activeTail"] = prev_joint

    for guide in guide_notes:
        connections = sorted(guide.midpoints, key=lambda n: n.beat)
        prev_note: Entity | None = None
        head_note: Entity | None = None
        connectors = []
        for note in connections:
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
                    "isSeparator": 0,
                    "segmentKind": GUIDE_COLORS[guide.color],
                    "segmentAlpha": 1,
                },
            )
            entities.append(entity)
            if head_note is None:
                head_note = entity
            if prev_note is not None:
                connector = Entity(
                    "Connector",
                    {
                        "head": prev_note,
                        "tail": entity,
                    },
                )
                entities.append(connector)
                connectors.append(connector)
                prev_note["next"] = entity
            prev_note = entity
        assert head_note is not None
        assert prev_note is not None
        for connector in connectors:
            connector["segmentHead"] = head_note
            connector["segmentTail"] = prev_note
            connector["activeHead"] = head_note
            connector["activeTail"] = prev_note
        match guide.fade:
            case "in":
                head_note["segmentAlpha"] = 0
            case "out":
                prev_note["segmentAlpha"] = 0
            case "none":
                pass
            case _:
                assert_never(guide.fade)

    leveldata = {
        "bgmOffset": score.metadata.waveoffset,
        "entities": [e.export() for e in entities],
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
