import base64
import gzip
import json
import io
import math
from pathlib import Path
from typing import IO

from ..notes.score import Score
from ..notes.bpm import Bpm
from ..notes.timescale import TimeScaleGroup
from ..notes.single import Single, Skill, FeverChance, FeverStart
from ..notes.slide import Slide, SlideStartPoint, SlideRelayPoint, SlideEndPoint
from ..notes.guide import Guide
from ..notes.volume import Volume

from .loader import _EASE_MAP_REV, _DIRECTION_MAP_REV


TICKS_PER_BEAT = 480


def _beat_to_ticks(beat: float) -> int:
    return round(beat * TICKS_PER_BEAT)


def _unconvert_lane(lane: float, size: float) -> tuple[int, int]:
    lane_start = math.floor(lane - size + 5.5 + 0.5)
    lane_end = math.floor(lane + size + 5.5 - 1 + 0.5)
    lane_start = max(0, min(11, lane_start))
    lane_end = max(0, min(11, lane_end))
    return lane_start, lane_end


def _get_note_base_type(
    category: int, is_start: bool, is_end: bool, is_single: bool
) -> int:
    # NoteBaseType: Base=0, Normal=1, Long=2, Flick=3, FrictionFlick=4,
    # Connection=5, HiddenConnection=6, LongHoldCombo=7, FrictionLong=8,
    # FrictionHideLong=9, Guide=10, Friction=11, FrictionHide=12,
    # GuideEnd=13, GuideHiddenConnection=14
    if is_single:
        match category:
            case 0:
                return 1  # Normal
            case 3:
                return 3  # Flick
            case 4:
                return 11  # Friction
            case 5:
                return 12  # FrictionHide
            case 8:
                return 4  # FrictionFlick
        return 1
    if is_start:
        match category:
            case 1:
                return 2  # Long
            case 6:
                return 8  # FrictionLong
            case 7:
                return 9  # FrictionHideLong
            case 9:
                return 10  # Guide
        return 2
    if is_end:
        match category:
            case 0 | 1:
                return 1  # Normal
            case 3:
                return 3  # Flick
            case 4:
                return 11  # Friction
            case 5:
                return 12  # FrictionHide
            case 8:
                return 4  # FrictionFlick
            case 10:
                return 13  # GuideEnd
        return 1
    # mid
    match category:
        case 2:
            return 5  # Connection
        case 13:
            return 6  # HiddenConnection
        case 11:
            return 14  # GuideHiddenConnection
    return 5


def export(
    path: str | Path | IO[bytes],
    score: Score,
    music_id: int,
) -> None:
    id_counter = 0
    ref_counter = 1

    def next_id() -> int:
        nonlocal id_counter
        id_counter += 1
        return id_counter

    def next_ref() -> str:
        nonlocal ref_counter
        ref_counter += 1
        return str(ref_counter)

    # -- EVENTS --
    event_list: list[dict] = []

    # Collect BPM, speed, and volume events
    for note in score.notes:
        if isinstance(note, Bpm):
            event_list.append(
                {
                    "$id": next_ref(),
                    "id": next_id(),
                    "eventType": 0,
                    "ticks": _beat_to_ticks(note.beat),
                    "changeValue": note.bpm,
                }
            )
        elif isinstance(note, TimeScaleGroup):
            for point in note.changes:
                event_list.append(
                    {
                        "$id": next_ref(),
                        "id": next_id(),
                        "eventType": 1,
                        "ticks": _beat_to_ticks(point.beat),
                        "changeValue": point.timeScale,
                    }
                )
        elif isinstance(note, Volume):
            event_list.append(
                {
                    "$id": next_ref(),
                    "id": next_id(),
                    "eventType": 2,
                    "ticks": _beat_to_ticks(note.beat),
                    "changeValue": note.volume,
                }
            )

    has_time_sig = any(e["eventType"] == 3 for e in event_list)
    if not has_time_sig:
        event_list.append(
            {
                "$id": next_ref(),
                "id": next_id(),
                "eventType": 3,
                "ticks": 0,
                "changeValue": "4/4",
            }
        )

    has_se_vol = any(e["eventType"] == 2 for e in event_list)
    if not has_se_vol:
        event_list.append(
            {
                "$id": next_ref(),
                "id": next_id(),
                "eventType": 2,
                "ticks": 0,
                "changeValue": 1.0,
            }
        )

    # -- NOTES --
    note_dicts: list[dict] = []
    max_ticks = 0

    def make_note(
        ticks: int,
        lane_start: int,
        lane_end: int,
        category: int,
        note_type: int,
        note_line_type: int,
        note_base_type: int,
        direction: int = 0,
        speed_ratio: float = 1.0,
        is_skip: bool = False,
        prev_id: int = -1,
        next_id_val: int = -1,
    ) -> dict:
        nonlocal max_ticks
        nid = next_id()
        if ticks > max_ticks:
            max_ticks = ticks

        return {
            "$id": next_ref(),
            "id": nid,
            "ticks": ticks,
            "laneStart": lane_start,
            "laneEnd": lane_end,
            "category": category,
            "type": note_type,
            "speedRatio": speed_ratio,
            "noteLineType": note_line_type,
            "noteBaseType": note_base_type,
            "previousConnectionId": prev_id,
            "nextConnectionId": next_id_val,
            "direction": direction,
            "isSkip": is_skip,
            "IsSingle": prev_id == -1 and next_id_val == -1,
            "IsConnectedFirst": prev_id == -1 and next_id_val != -1,
            "IsConnectedLast": prev_id != -1 and next_id_val == -1,
        }

    for note in score.notes:
        if isinstance(
            note, (Bpm, TimeScaleGroup, Volume, Skill, FeverChance, FeverStart)
        ):
            continue

        if isinstance(note, Single):
            ticks = _beat_to_ticks(note.beat)
            lane_start, lane_end = _unconvert_lane(note.lane, note.size)
            critical = 1 if note.critical else 0
            direction = _DIRECTION_MAP_REV.get(note.direction, 0)

            if note.trace and note.direction:
                category = 8  # FrictionFlick
            elif note.trace:
                category = 4  # Friction
            elif note.direction:
                category = 3  # Flick
            else:
                category = 0  # Normal

            note_base_type = _get_note_base_type(category, False, False, True)
            note_dicts.append(
                make_note(
                    ticks=ticks,
                    lane_start=lane_start,
                    lane_end=lane_end,
                    category=category,
                    note_type=critical,
                    note_line_type=0,
                    note_base_type=note_base_type,
                    direction=direction,
                    speed_ratio=note.speedRatio,
                )
            )

        elif isinstance(note, Slide):
            chain_notes: list[dict] = []
            reserved_ids = list(
                range(id_counter + 1, id_counter + 1 + len(note.connections))
            )

            for i, conn in enumerate(note.connections):
                ticks = _beat_to_ticks(conn.beat)
                lane_start, lane_end = _unconvert_lane(conn.lane, conn.size)
                note_line_type = _EASE_MAP_REV.get(getattr(conn, "ease", "linear"), 0)

                if i == 0:
                    assert isinstance(conn, SlideStartPoint)
                    critical = 1 if conn.critical else 0
                    if conn.judgeType == "none":
                        category = 7  # FrictionHideLong
                    elif conn.judgeType == "trace":
                        category = 6  # FrictionLong
                    else:
                        category = 1  # Long
                    note_base_type = _get_note_base_type(category, True, False, False)
                    direction = 0
                    is_skip = False
                    prev_conn = -1
                    next_conn = reserved_ids[i + 1] if i + 1 < len(reserved_ids) else -1
                elif i == len(note.connections) - 1:
                    assert isinstance(conn, SlideEndPoint)
                    critical = 1 if conn.critical else 0
                    direction = _DIRECTION_MAP_REV.get(conn.direction, 0)

                    if conn.direction and conn.judgeType == "trace":
                        category = 8  # FrictionFlick
                    elif conn.judgeType == "trace":
                        category = 4  # Friction
                    elif conn.judgeType == "none":
                        category = 5  # FrictionHide
                    elif conn.direction:
                        category = 3  # Flick
                    else:
                        category = 1  # Long

                    note_base_type = _get_note_base_type(category, False, True, False)
                    is_skip = False
                    prev_conn = reserved_ids[i - 1]
                    next_conn = -1
                else:
                    assert isinstance(conn, SlideRelayPoint)
                    critical = 1 if conn.critical else 0

                    if conn.critical is None:
                        category = 13  # Hidden
                        critical = 1 if note.critical else 0
                    else:
                        category = 2  # Connection

                    note_base_type = _get_note_base_type(category, False, False, False)
                    direction = 0
                    is_skip = conn.type == "attach"
                    prev_conn = reserved_ids[i - 1]
                    next_conn = reserved_ids[i + 1] if i + 1 < len(reserved_ids) else -1

                nid = reserved_ids[i]
                if ticks > max_ticks:
                    max_ticks = ticks

                n = {
                    "$id": next_ref(),
                    "id": nid,
                    "ticks": ticks,
                    "laneStart": lane_start,
                    "laneEnd": lane_end,
                    "category": category,
                    "type": critical,
                    "speedRatio": conn.speedRatio,
                    "noteLineType": note_line_type,
                    "noteBaseType": note_base_type,
                    "previousConnectionId": prev_conn,
                    "nextConnectionId": next_conn,
                    "direction": direction if i == len(note.connections) - 1 else 0,
                    "isSkip": is_skip,
                    "IsSingle": False,
                    "IsConnectedFirst": i == 0,
                    "IsConnectedLast": i == len(note.connections) - 1,
                }
                chain_notes.append(n)

            id_counter = reserved_ids[-1]
            note_dicts.extend(chain_notes)

        elif isinstance(note, Guide):
            reserved_ids = list(
                range(id_counter + 1, id_counter + 1 + len(note.midpoints))
            )

            for i, mp in enumerate(note.midpoints):
                ticks = _beat_to_ticks(mp.beat)
                lane_start, lane_end = _unconvert_lane(mp.lane, mp.size)
                note_line_type = _EASE_MAP_REV.get(mp.ease, 0)
                critical = 1 if note.color == "yellow" else 0

                if i == 0:
                    category = 9  # Guide
                    note_base_type = 10  # Guide
                elif i == len(note.midpoints) - 1:
                    category = 10  # GuideEnd
                    note_base_type = 13
                    note_line_type = 0  # GuideEnd forces linear
                else:
                    category = 11  # GuideHidden
                    note_base_type = 14  # GuideHiddenConnection

                prev_conn = reserved_ids[i - 1] if i > 0 else -1
                next_conn = reserved_ids[i + 1] if i + 1 < len(reserved_ids) else -1

                nid = reserved_ids[i]
                if ticks > max_ticks:
                    max_ticks = ticks

                note_dicts.append(
                    {
                        "$id": next_ref(),
                        "id": nid,
                        "ticks": ticks,
                        "laneStart": lane_start,
                        "laneEnd": lane_end,
                        "category": category,
                        "type": critical,
                        "speedRatio": mp.speedRatio,
                        "noteLineType": note_line_type,
                        "noteBaseType": note_base_type,
                        "previousConnectionId": prev_conn,
                        "nextConnectionId": next_conn,
                        "direction": 0,
                        "isSkip": False,
                        "IsSingle": False,
                        "IsConnectedFirst": i == 0,
                        "IsConnectedLast": i == len(note.midpoints) - 1,
                    }
                )

            id_counter = reserved_ids[-1]

    pjsk_data = {
        "$id": "1",
        "VersionCode": 10000,
        "MusicScoreEventDataList": event_list,
        "EventArray": [],
        "NoteList": note_dicts,
        "MusicScoreTicksMax": max_ticks,
        "MusicId": music_id,
        "FullComboDataHash": "",
    }

    json_bytes = json.dumps(pjsk_data, separators=(",", ":")).encode("utf-8")
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        gz.write(json_bytes)
    encoded = base64.b64encode(buf.getvalue())

    if isinstance(path, (str, Path)):
        with open(path, "wb") as f:
            f.write(encoded)
    else:
        path.write(encoded)
