from copy import deepcopy
from dataclasses import dataclass, asdict

from .metadata import MetaData, validate_metadata_dict_values
from .bpm import Bpm, validate_bpm_dict_values
from .timescale import TimeScaleGroup, TimeScalePoint, validate_timescale_dict_values
from .single import (
    Single,
    Skill,
    FeverChance,
    FeverStart,
    validate_single_dict_values,
    validate_event_dict_values,
)
from .slide import (
    Slide,
    SlideStartPoint,
    SlideRelayPoint,
    SlideEndPoint,
    validate_slide_dict_values,
)
from .guide import Guide, GuidePoint, validate_guide_dict_values
from .volume import Volume, validate_volume_dict_values


def usc_lanes_to_sus_lanes(lane: float, size: float) -> int:
    return int(lane - size + 8)


# 1tickをbeatに変換
BEAT_PER_TICK = round(4 / 1920, 6)

# ノーツリストを何小節区切りにするか
# ※ノーツリスト = 重なりを調べるときに使用するリスト
BAR_INTERVAL = 0.5

# uscのレーン表記(中央が0.0)
# ↓
# 左端を1に変換するオフセット
LANE_OFFSET = 7


# ノーツの範囲を計算する
# [ 1 2 3 4 5 6 7 8 9 10 11 12 ] で占有レーンを表記する
def _calc_note_range(lane: float, size: float) -> list[int]:
    note_leftpos = int(lane - size + LANE_OFFSET)
    note_size = int(size * 2)
    return [_ for _ in range(note_leftpos, note_leftpos + note_size)]


# ノーツを入れるリストの番号をbeatの値から計算する
def _calc_notelist_index(
    note: Single | SlideStartPoint | SlideRelayPoint | SlideEndPoint | GuidePoint,
) -> int:
    return int(note.beat // BAR_INTERVAL)


# BAR_INTERVALごとに区切ってノーツを入れたリストから、指定beatのリストと前後のリストにあるノーツを返す
def _get_target_notelist(
    split_tmp_notes: list[
        list[Single | SlideStartPoint | SlideRelayPoint | SlideEndPoint | GuidePoint]
    ],
    target_note: (
        Single | SlideStartPoint | SlideRelayPoint | SlideEndPoint | GuidePoint
    ),
) -> list[Single | SlideStartPoint | SlideRelayPoint | SlideEndPoint | GuidePoint]:
    index = _calc_notelist_index(target_note)
    start = max(0, index - 1)
    end = min(len(split_tmp_notes), index + 2)
    return sum(split_tmp_notes[start:end], [])


# スライド、ガイドのpointを入れたリストを返す
def _convert_tmp_notes(
    tmp_notes: list[Single | Slide | Guide],
) -> list[Single | SlideStartPoint | SlideRelayPoint | SlideEndPoint | GuidePoint]:
    tmp = []
    for note in tmp_notes:
        if isinstance(note, Slide):
            for i in note.connections:
                tmp.append(i)
        elif isinstance(note, Guide):
            for i in note.midpoints:
                tmp.append(i)
        else:
            tmp.append(note)
    return tmp


# ノーツの一部または全てが重なっているか調べる
def _get_overlap_note(
    target_note: (
        Single | SlideStartPoint | SlideRelayPoint | SlideEndPoint | GuidePoint
    ),
    split_tmp_notes: list[
        list[Single | SlideStartPoint | SlideRelayPoint | SlideEndPoint | GuidePoint]
    ],
) -> Single | SlideStartPoint | SlideRelayPoint | SlideEndPoint | GuidePoint | None:

    t_note_range = set(_calc_note_range(target_note.lane, target_note.size))
    t_note_beat = target_note.beat

    for note in _get_target_notelist(split_tmp_notes, target_note):
        # 同じインスタンス（ノーツ）の場合は飛ばす
        if target_note is note:
            continue
        # 同じ拍、かつノーツの一部または全てが重なっているか判定
        note_range = _calc_note_range(note.lane, note.size)
        if t_note_beat == note.beat and bool(t_note_range.intersection(note_range)):
            return note

    return None


# スライドが脱法（終点より後に中継点があるetc...）していないか調べ、修正する
def _check_slide(
    note: Slide,
    split_tmp_notes: list[
        list[
            Single
            | Skill
            | FeverStart
            | FeverChance
            | SlideStartPoint
            | SlideRelayPoint
            | SlideEndPoint
            | GuidePoint
        ]
    ],
):
    for point in note.connections:
        if isinstance(point, SlideStartPoint):
            start_point = point
        elif isinstance(point, SlideEndPoint):
            end_point = point

    for point in note.connections:

        if not isinstance(point, SlideEndPoint):
            while point.beat >= end_point.beat:
                point.beat -= BEAT_PER_TICK
                while _get_overlap_note(point, split_tmp_notes) != None:
                    point.beat -= BEAT_PER_TICK

        if not isinstance(point, SlideStartPoint):
            while point.beat <= start_point.beat:
                point.beat += BEAT_PER_TICK
                while _get_overlap_note(point, split_tmp_notes) != None:
                    point.beat += BEAT_PER_TICK

        if point.beat > end_point.beat:
            point.beat, end_point.beat = end_point.beat, point.beat


def _shift_slide(note: Slide, split_tmp_notes: list[Single | Slide | Guide]):
    for point in note.connections:
        while (overlap_note := _get_overlap_note(point, split_tmp_notes)) != None:
            match point, overlap_note:

                # スライド始点 + single
                case SlideStartPoint(), Single():
                    if point.judgeType != "none" and overlap_note.trace:
                        overlap_note.beat += BEAT_PER_TICK
                    else:
                        point.beat += BEAT_PER_TICK

                # スライド始点 + スライド始点
                case SlideStartPoint(), SlideStartPoint():
                    if point.judgeType != "none" and overlap_note.judgeType == "none":
                        overlap_note.beat += BEAT_PER_TICK
                    else:
                        point.beat += BEAT_PER_TICK

                # スライド始点 + スライド中継点
                case SlideStartPoint(), SlideRelayPoint():
                    overlap_note.beat += BEAT_PER_TICK

                # スライド始点 + スライド終点
                case SlideStartPoint(), SlideEndPoint():
                    point.beat += BEAT_PER_TICK

                # スライド中継点 + ノーツ
                case SlideRelayPoint(), _:
                    point.beat += BEAT_PER_TICK

                # スライド終点 + single
                case SlideEndPoint(), Single():
                    point.beat -= BEAT_PER_TICK

                # スライド終点 + スライド始点
                case SlideEndPoint(), SlideStartPoint():
                    overlap_note.beat += BEAT_PER_TICK

                # スライド終点 + スライド中継点
                case SlideEndPoint(), SlideRelayPoint():
                    overlap_note.beat += BEAT_PER_TICK

                # スライド終点 + スライド終点
                case SlideEndPoint(), SlideEndPoint():
                    if point.judgeType == "none" or overlap_note.direction != None:
                        point.beat -= BEAT_PER_TICK
                    elif overlap_note.judgeType == "none" or point.direction != None:
                        overlap_note.beat -= BEAT_PER_TICK
                    else:
                        point.beat -= BEAT_PER_TICK

                case SlideEndPoint(), _:
                    point.beat -= BEAT_PER_TICK

                case _, _:
                    point.beat += BEAT_PER_TICK

    _check_slide(note, split_tmp_notes)


def _shift_guide(note: Guide, split_tmp_notes: list[Single | Slide | Guide]):
    for point in note.midpoints:
        while _get_overlap_note(point, split_tmp_notes) != None:
            point.beat += BEAT_PER_TICK

    note.midpoints.sort(key=lambda x: x.beat)


def _shift_single(note: Single, split_tmp_notes: list[Single | Slide | Guide]):
    while (overlap_note := _get_overlap_note(note, split_tmp_notes)) != None:
        match note, overlap_note:
            case _, Single(trace=True):
                overlap_note.beat += BEAT_PER_TICK
            case _, SlideStartPoint():
                overlap_note.beat += BEAT_PER_TICK
            case _, SlideRelayPoint():
                overlap_note.beat += BEAT_PER_TICK
            case _, SlideEndPoint():
                overlap_note.beat -= BEAT_PER_TICK
            case _, GuidePoint():
                overlap_note.beat += BEAT_PER_TICK
            case _, _:
                note.beat += BEAT_PER_TICK


# CUT HELPERS
# When cutting slides/guides at a boundary:
# - Linear ease: interpolate lane/size at the cut beat
# - Non-linear ease: snap to nearest relay point, or delete if none
# - Truncated starts/ends become headless (judgeType="none")


def _lerp_point(a, b, beat: float) -> tuple[float, float]:
    ratio = (beat - a.beat) / (b.beat - a.beat)
    return (
        round(a.lane + ratio * (b.lane - a.lane), 6),
        round(a.size + ratio * (b.size - a.size), 6),
    )


def _truncate_slide_start(
    conns: list[SlideStartPoint | SlideRelayPoint | SlideEndPoint],
    start_beat: float,
    critical: bool,
) -> list[SlideStartPoint | SlideRelayPoint | SlideEndPoint] | None:
    first_in = None
    last_before = None
    for i, conn in enumerate(conns):
        if conn.beat >= start_beat:
            first_in = i
            break
        last_before = i

    if first_in is None:
        return None

    if conns[first_in].beat == start_beat:
        result = list(conns[first_in:])
        p = result[0]
        result[0] = SlideStartPoint(
            beat=start_beat,
            critical=critical,
            ease=p.ease if hasattr(p, "ease") else "linear",
            judgeType="none",
            lane=p.lane,
            size=p.size,
            timeScaleGroup=p.timeScaleGroup,
            speedRatio=p.speedRatio,
        )
        return result if len(result) >= 2 else None

    prev = conns[last_before] if last_before is not None else None
    next_p = conns[first_in]

    if prev is not None and hasattr(prev, "ease") and prev.ease == "linear":
        lane, size = _lerp_point(prev, next_p, start_beat)
        new_start = SlideStartPoint(
            beat=start_beat,
            critical=critical,
            ease="linear",
            judgeType="none",
            lane=lane,
            size=size,
            timeScaleGroup=next_p.timeScaleGroup,
            speedRatio=next_p.speedRatio,
        )
        result = [new_start] + list(conns[first_in:])
        return result if len(result) >= 2 else None

    # Non-linear ease: snap to first in-range point.
    # If only the end remains, not enough for a valid slide.
    if isinstance(next_p, SlideEndPoint):
        return None
    result = list(conns[first_in:])
    p = result[0]
    result[0] = SlideStartPoint(
        beat=p.beat,
        critical=critical,
        ease=p.ease if hasattr(p, "ease") else "linear",
        judgeType="none",
        lane=p.lane,
        size=p.size,
        timeScaleGroup=p.timeScaleGroup,
        speedRatio=p.speedRatio,
    )
    return result if len(result) >= 2 else None


def _truncate_slide_end(
    conns: list[SlideStartPoint | SlideRelayPoint | SlideEndPoint],
    end_beat: float,
    critical: bool,
) -> list[SlideStartPoint | SlideRelayPoint | SlideEndPoint] | None:
    last_in = None
    first_after = None
    for i, conn in enumerate(conns):
        if conn.beat <= end_beat:
            last_in = i
        elif first_after is None:
            first_after = i

    if last_in is None:
        return None

    if conns[last_in].beat == end_beat:
        result = list(conns[: last_in + 1])
        p = result[-1]
        result[-1] = SlideEndPoint(
            beat=end_beat,
            critical=critical,
            judgeType="none",
            lane=p.lane,
            size=p.size,
            timeScaleGroup=p.timeScaleGroup,
            speedRatio=p.speedRatio,
        )
        return result if len(result) >= 2 else None

    last_p = conns[last_in]
    next_p = conns[first_after] if first_after is not None else None

    if next_p is not None and hasattr(last_p, "ease") and last_p.ease == "linear":
        lane, size = _lerp_point(last_p, next_p, end_beat)
        new_end = SlideEndPoint(
            beat=end_beat,
            critical=critical,
            judgeType="none",
            lane=lane,
            size=size,
            timeScaleGroup=last_p.timeScaleGroup,
            speedRatio=last_p.speedRatio,
        )
        result = list(conns[: last_in + 1]) + [new_end]
        return result if len(result) >= 2 else None

    # Non-linear ease or no next: snap to last in-range point.
    # If only the start remains, not enough for a valid slide.
    if isinstance(last_p, SlideStartPoint):
        return None
    result = list(conns[: last_in + 1])
    p = result[-1]
    result[-1] = SlideEndPoint(
        beat=p.beat,
        critical=critical,
        judgeType="none",
        lane=p.lane,
        size=p.size,
        timeScaleGroup=p.timeScaleGroup,
        speedRatio=p.speedRatio,
    )
    return result if len(result) >= 2 else None


def _truncate_guide_start(
    mps: list[GuidePoint], start_beat: float
) -> list[GuidePoint] | None:
    first_in = None
    last_before = None
    for i, mp in enumerate(mps):
        if mp.beat >= start_beat:
            first_in = i
            break
        last_before = i

    if first_in is None:
        return None

    if mps[first_in].beat == start_beat:
        result = list(mps[first_in:])
        return result if len(result) >= 2 else None

    prev = mps[last_before] if last_before is not None else None

    if prev is not None and prev.ease == "linear":
        lane, size = _lerp_point(prev, mps[first_in], start_beat)
        new_start = GuidePoint(
            beat=start_beat,
            ease="linear",
            lane=lane,
            size=size,
            timeScaleGroup=mps[first_in].timeScaleGroup,
            speedRatio=mps[first_in].speedRatio,
        )
        result = [new_start] + list(mps[first_in:])
        return result if len(result) >= 2 else None

    result = list(mps[first_in:])
    return result if len(result) >= 2 else None


def _truncate_guide_end(
    mps: list[GuidePoint], end_beat: float
) -> list[GuidePoint] | None:
    last_in = None
    first_after = None
    for i, mp in enumerate(mps):
        if mp.beat <= end_beat:
            last_in = i
        elif first_after is None:
            first_after = i

    if last_in is None:
        return None

    if mps[last_in].beat == end_beat:
        result = list(mps[: last_in + 1])
        return result if len(result) >= 2 else None

    last_mp = mps[last_in]
    next_mp = mps[first_after] if first_after is not None else None

    if next_mp is not None and last_mp.ease == "linear":
        lane, size = _lerp_point(last_mp, next_mp, end_beat)
        new_end = GuidePoint(
            beat=end_beat,
            ease="linear",
            lane=lane,
            size=size,
            timeScaleGroup=last_mp.timeScaleGroup,
            speedRatio=last_mp.speedRatio,
        )
        return list(mps[: last_in + 1]) + [new_end]

    result = list(mps[: last_in + 1])
    return result if len(result) >= 2 else None


def usc_remove_fake_field(notes: list) -> list:
    for note in notes:
        note.pop("fake", 0)
        if "connectors" in note:
            for c in note["connectors"]:
                c.pop("fake", 0)
        if "midpoints" in note:
            for m in note["midpoints"]:
                m.pop("fake", 0)


class InvalidNoteError(Exception):
    def __init__(self, note: dict, t: str, error_message: str):
        self.note = note
        self.error_message = error_message
        super().__init__(f"Invalid {t} note: {self.note}. Error: {self.error_message}")


@dataclass
class Score:
    metadata: MetaData
    notes: list[
        Bpm
        | TimeScaleGroup
        | Volume
        | Single
        | Skill
        | FeverStart
        | FeverChance
        | Slide
        | Guide
    ]

    def validate(self) -> bool:
        metadata_validation = validate_metadata_dict_values(self.metadata.__dict__)
        if metadata_validation:
            note_dict, error_message = metadata_validation
            raise InvalidNoteError(note_dict, "MetaData", error_message)

        for note in self.notes:
            note_dict = asdict(note)
            if isinstance(note, (Skill, FeverStart, FeverChance)):
                validation_result = validate_event_dict_values(note_dict)
                if validation_result:
                    note_dict, error_message = validation_result
                    raise InvalidNoteError(note_dict, note.type, error_message)
            elif isinstance(note, Bpm):
                validation_result = validate_bpm_dict_values(note_dict)
                if validation_result:
                    note_dict, error_message = validation_result
                    raise InvalidNoteError(note_dict, "BPM", error_message)
            elif isinstance(note, TimeScaleGroup):
                validation_result = validate_timescale_dict_values(note_dict)
                if validation_result:
                    note_dict, error_message = validation_result
                    raise InvalidNoteError(note_dict, "TimeScaleGroup", error_message)
            elif isinstance(note, Single):
                validation_result = validate_single_dict_values(note_dict)
                if validation_result:
                    note_dict, error_message = validation_result
                    raise InvalidNoteError(note_dict, "Single", error_message)
            elif isinstance(note, Slide):
                validation_result = validate_slide_dict_values(note_dict)
                if validation_result:
                    note_dict, error_message = validation_result
                    raise InvalidNoteError(note_dict, "Slide", error_message)
            elif isinstance(note, Guide):
                validation_result = validate_guide_dict_values(note_dict)
                if validation_result:
                    note_dict, error_message = validation_result
                    raise InvalidNoteError(note_dict, "Guide", error_message)
            elif isinstance(note, Volume):
                validation_result = validate_volume_dict_values(note_dict)
                if validation_result:
                    note_dict, error_message = validation_result
                    raise InvalidNoteError(note_dict, "Volume", error_message)
            else:
                raise InvalidNoteError(
                    note_dict, "UNKNOWN NOTE TYPE", "Invalid note type in list."
                )
        return True

    def delete_fake_notes(self):
        notes = []
        for note in self.notes:
            if hasattr(note, "fake") and note.fake:
                pass
            else:
                notes.append(note)
        self.notes = notes

    def delete_damage_notes(self):
        notes = []
        for note in self.notes:
            if isinstance(note, Single) and note.type == "damage":
                pass
            else:
                notes.append(note)
        self.notes = notes

    def replace_extended_guide_colors(
        self,
        color_map: dict = {
            "neutral": "green",
            "red": "yellow",
            "green": "green",
            "blue": "green",
            "yellow": "yellow",
            "purple": "yellow",
            "cyan": "green",
            "black": "green",
        },
    ):
        for note in self.notes:
            if not isinstance(note, Guide):
                continue
            note.color = color_map[note.color]

    def replace_extended_ease(self):
        # XXX: Probably better to add an attach tick halfway, then switch ease
        # If anyone wants to PR this, feel free!
        ease_map = {
            "outin": "in",
            "out": "out",
            "linear": "linear",
            "in": "in",
            "inout": "out",
        }
        for note in self.notes:
            if not isinstance(note, (Slide, Guide)):
                continue
            if isinstance(note, Slide):
                for c in note.connections:
                    if hasattr(c, "ease"):
                        c.ease = ease_map[c.ease]
            if isinstance(note, Guide):
                for m in note.midpoints:
                    m.ease = ease_map[m.ease]

    def sort_by_beat(self):
        self.notes = sorted(
            self.notes,
            key=lambda x: (
                x.beat
                if hasattr(x, "beat")
                else (
                    x.connections[0].beat
                    if hasattr(x, "connections")
                    else (
                        x.midpoints[0].beat
                        if hasattr(x, "midpoints")
                        else x.changes[0].beat
                    )
                )
            ),
        )

    # フェードなしガイドの中継点を生成する
    def add_point_without_fade(self):
        for note in self.notes:
            if not isinstance(note, Guide):
                continue
            if note.fade == "none":
                end_point = note.midpoints[-1]
                note.append(
                    GuidePoint(
                        beat=end_point.beat - BEAT_PER_TICK,
                        ease="linear",
                        lane=end_point.lane,
                        size=end_point.size,
                        timeScaleGroup=end_point.timeScaleGroup,
                    )
                )

    def strip_extended_lanes(self, resize_if_possible: bool = False):
        """
        This is a very crude function that deletes any notes with a lane value not supported in the base game.

        resize_if_possible: attempts to resize the note to fit.
        - If not enabled, if the note starts OR ends outside, it'll be deleted.
        - If enabled, a note fully outside is deleted, however a note with any part inside the main lanes will be kept.

        Slides/Guides that have a start/end outside the lanes are fully deleted, otherwise only the connectors are deleted.
        """
        notes = []
        max_lane = 6
        min_lane = -6
        for note in self.notes:
            if (
                isinstance(note, Bpm)
                or isinstance(note, TimeScaleGroup)
                or isinstance(note, (Skill, FeverStart, FeverChance, Volume))
            ):
                notes.append(note)
                continue
            if isinstance(note, Single):
                # note.lane 0 (+1/-1 for each lane, based on middle of note, starting at center lane)
                # note.size +0.5 for each lane.
                lane_start = note.lane - note.size
                lane_end = note.lane + note.size
                if lane_start < min_lane:
                    if resize_if_possible and (lane_end > min_lane):
                        # shift the left end, then the middle
                        extra = abs(lane_start - min_lane)
                        note.size -= extra / 2
                        note.lane += extra / 2
                if lane_end > max_lane:
                    if (
                        resize_if_possible
                        and (lane_start < max_lane)
                        and (lane_start >= min_lane)
                    ):
                        # shift the right end, then the middle
                        extra = abs(lane_end - max_lane)
                        note.size -= extra / 2
                        note.lane -= extra / 2
                lane_start = note.lane - note.size
                lane_end = note.lane + note.size
                if lane_start >= min_lane and lane_end <= max_lane:
                    notes.append(note)
            if isinstance(note, Slide):
                connectors = []
                should_add = True
                for i, connector in enumerate(note.connections):
                    lane_start = connector.lane - connector.size
                    lane_end = connector.lane + connector.size
                    added = False
                    if lane_start < min_lane:
                        if resize_if_possible and (lane_end > min_lane):
                            # shift the left end, then the middle
                            extra = abs(lane_start - min_lane)
                            connector.size -= extra / 2
                            connector.lane += extra / 2
                    if lane_end > max_lane:
                        if (
                            resize_if_possible
                            and (lane_start < max_lane)
                            and (lane_start >= min_lane)
                        ):
                            # shift the right end, then the middle
                            extra = abs(lane_end - max_lane)
                            connector.size -= extra / 2
                            connector.lane -= extra / 2
                    lane_start = connector.lane - connector.size
                    lane_end = connector.lane + connector.size
                    if lane_start >= min_lane and lane_end <= max_lane:
                        connectors.append(connector)
                        added = True
                    if (i == 0 or i == len(note.connections) - 1) and not added:
                        should_add = False
                if should_add:
                    notes.append(
                        Slide(
                            critical=note.critical,
                            connections=connectors,
                            type=note.type,
                        )
                    )
            if isinstance(note, Guide):
                midpoints = []
                should_add = True
                for i, midpoint in enumerate(note.midpoints):
                    lane_start = midpoint.lane - midpoint.size
                    lane_end = midpoint.lane + midpoint.size
                    added = False
                    if lane_start < min_lane:
                        if resize_if_possible and (lane_end > min_lane):
                            # shift the left end, then the middle
                            extra = abs(lane_start - min_lane)
                            midpoint.size -= extra / 2
                            midpoint.lane += extra / 2
                    if lane_end > max_lane:
                        if (
                            resize_if_possible
                            and (lane_start < max_lane)
                            and (lane_start >= min_lane)
                        ):
                            # shift the right end, then the middle
                            extra = abs(lane_end - max_lane)
                            midpoint.size -= extra / 2
                            midpoint.lane -= extra / 2
                    lane_start = midpoint.lane - midpoint.size
                    lane_end = midpoint.lane + midpoint.size
                    if lane_start >= min_lane and lane_end <= max_lane:
                        midpoints.append(midpoint)
                        added = True
                    if (i == 0 or i == len(note.midpoints) - 1) and not added:
                        should_add = False
                if should_add:
                    notes.append(
                        Guide(
                            note.color,
                            fade=note.fade,
                            midpoints=midpoints,
                            type=note.type,
                        )
                    )
        self.notes = notes

    def strip_speed_ratios(self) -> None:
        for note in self.notes:
            if isinstance(note, Single):
                note.speedRatio = 1.0
            elif isinstance(note, Slide):
                for conn in note.connections:
                    conn.speedRatio = 1.0
            elif isinstance(note, Guide):
                for mp in note.midpoints:
                    mp.speedRatio = 1.0

    def flatten_speed_ratios_to_layers(self) -> None:
        tsg_indices: list[int] = []
        for i, note in enumerate(self.notes):
            if isinstance(note, TimeScaleGroup):
                tsg_indices.append(i)

        unique_ratios: set[float] = set()
        for note in self.notes:
            if isinstance(note, Single) and note.speedRatio != 1.0:
                unique_ratios.add(note.speedRatio)
            elif isinstance(note, Slide):
                for conn in note.connections:
                    if conn.speedRatio != 1.0:
                        unique_ratios.add(conn.speedRatio)
            elif isinstance(note, Guide):
                for mp in note.midpoints:
                    if mp.speedRatio != 1.0:
                        unique_ratios.add(mp.speedRatio)

        if not unique_ratios:
            return

        next_group_idx = len(tsg_indices)
        ratio_to_group: dict[float, int] = {}
        new_groups: list[TimeScaleGroup] = []
        for ratio in sorted(unique_ratios):
            ratio_to_group[ratio] = next_group_idx
            new_groups.append(
                TimeScaleGroup(changes=[TimeScalePoint(beat=0.0, timeScale=ratio)])
            )
            next_group_idx += 1

        self.notes.extend(new_groups)

        for note in self.notes:
            if isinstance(note, Single) and note.speedRatio != 1.0:
                note.timeScaleGroup = ratio_to_group[note.speedRatio]
                note.speedRatio = 1.0
            elif isinstance(note, Slide):
                for conn in note.connections:
                    if conn.speedRatio != 1.0:
                        conn.timeScaleGroup = ratio_to_group[conn.speedRatio]
                        conn.speedRatio = 1.0
            elif isinstance(note, Guide):
                for mp in note.midpoints:
                    if mp.speedRatio != 1.0:
                        mp.timeScaleGroup = ratio_to_group[mp.speedRatio]
                        mp.speedRatio = 1.0

    def check_skill_overlap(self) -> bool:
        skill_timings = []
        for note in self.notes:
            if isinstance(note, Skill):
                if note.beat in skill_timings:
                    return True
                skill_timings.append(note.beat)
        return False

    def export_overlaps_score(self) -> tuple["Score", int]:
        tmp_notes = []

        useful_notes = []
        # 一旦、中継点灯を含めた全部のノーツを入れたリストを作る（BPM, ソフランは除外）
        for note in self.notes:
            if (
                isinstance(note, Bpm)
                or isinstance(note, TimeScaleGroup)
                or isinstance(note, (Skill, FeverStart, FeverChance, Volume))
            ):
                useful_notes.append(note)
                continue
            tmp_notes.append(note)
        tmp_notes = _convert_tmp_notes(tmp_notes)

        used = {}
        added_used = []
        overlaps_at = []
        for note in tmp_notes:
            if (note.beat, usc_lanes_to_sus_lanes(note.lane, note.size)) in used.keys():
                if (
                    note.beat,
                    usc_lanes_to_sus_lanes(note.lane, note.size),
                ) not in added_used:
                    added_used.append(
                        (note.beat, usc_lanes_to_sus_lanes(note.lane, note.size))
                    )
                    overlaps_at.append(
                        used[(note.beat, usc_lanes_to_sus_lanes(note.lane, note.size))]
                    )
                overlaps_at.append(
                    (note.beat, note.lane, note.size, note.timeScaleGroup)
                )
            else:
                used[(note.beat, usc_lanes_to_sus_lanes(note.lane, note.size))] = (
                    note.beat,
                    note.lane,
                    note.size,
                    note.timeScaleGroup,
                )
        score = Score(
            metadata=self.metadata,
            notes=useful_notes
            + [
                Single(
                    beat=d[0],
                    critical=True,
                    lane=d[1],
                    size=d[2],
                    timeScaleGroup=d[3],
                    trace=False,
                    direction=None,
                )
                for d in overlaps_at
            ],
        )
        return score, len(overlaps_at)

    # 重なっているノーツをずらす
    def shift(self):
        tmp_notes = []

        for note in self.notes:
            if (
                isinstance(note, Bpm)
                or isinstance(note, TimeScaleGroup)
                or isinstance(note, (Skill, FeverStart, FeverChance, Volume))
            ):
                continue
            tmp_notes.append(note)
        tmp_notes = _convert_tmp_notes(tmp_notes)

        max_beat = max(tmp_notes, key=lambda x: x.beat).beat

        split_tmp_notes = [list() for _ in range(int(max_beat // BAR_INTERVAL + 1))]

        for note in tmp_notes:
            split_tmp_notes[_calc_notelist_index(note)].append(note)

        for note in self.notes:
            if (
                isinstance(note, Bpm)
                or isinstance(note, TimeScaleGroup)
                or isinstance(note, (Skill, FeverStart, FeverChance, Volume))
            ):
                continue

            if isinstance(note, Single):
                _shift_single(note, split_tmp_notes)
            elif isinstance(note, Slide):
                _shift_slide(note, split_tmp_notes)
            elif isinstance(note, Guide):
                _shift_guide(note, split_tmp_notes)

    def _bpm_timeline(self) -> list[tuple[float, float]]:
        bpms = sorted(
            [n for n in self.notes if isinstance(n, Bpm)], key=lambda b: b.beat
        )
        if not bpms:
            return [(0.0, 120.0)]
        if bpms[0].beat > 0:
            bpms.insert(0, Bpm(beat=0.0, bpm=bpms[0].bpm))
        return [(b.beat, b.bpm) for b in bpms]

    def time_at_beat(self, target_beat: float) -> float:
        timeline = self._bpm_timeline()
        elapsed = 0.0
        for i, (beat, bpm) in enumerate(timeline):
            next_beat = timeline[i + 1][0] if i + 1 < len(timeline) else target_beat
            segment_end = min(next_beat, target_beat)
            if segment_end > beat:
                elapsed += (segment_end - beat) / bpm * 60.0
            if segment_end >= target_beat:
                break
        return elapsed

    def beat_at_time(self, target_time: float) -> float:
        timeline = self._bpm_timeline()
        elapsed = 0.0
        for i, (beat, bpm) in enumerate(timeline):
            next_beat = timeline[i + 1][0] if i + 1 < len(timeline) else float("inf")
            segment_duration = (next_beat - beat) / bpm * 60.0
            if elapsed + segment_duration >= target_time:
                remaining = target_time - elapsed
                return beat + remaining * bpm / 60.0
            elapsed += segment_duration
        last_beat, last_bpm = timeline[-1]
        remaining = target_time - elapsed
        return last_beat + remaining * last_bpm / 60.0

    def _note_beat(
        self,
        note: "Bpm | TimeScaleGroup | Single | Skill | FeverStart | FeverChance | Slide | Guide",
    ) -> float:
        if hasattr(note, "beat"):
            return note.beat
        if isinstance(note, Slide):
            return note.connections[0].beat
        if isinstance(note, Guide):
            return note.midpoints[0].beat
        if isinstance(note, TimeScaleGroup):
            return note.changes[0].beat
        return 0.0

    def _note_max_beat(
        self,
        note: "Bpm | TimeScaleGroup | Single | Skill | FeverStart | FeverChance | Slide | Guide",
    ) -> float:
        if isinstance(note, Slide):
            return note.connections[-1].beat
        if isinstance(note, Guide):
            return note.midpoints[-1].beat
        if isinstance(note, TimeScaleGroup):
            return note.changes[-1].beat
        return self._note_beat(note)

    @property
    def duration(self) -> float:
        max_beat = 0.0
        for note in self.notes:
            mb = self._note_max_beat(note)
            if mb > max_beat:
                max_beat = mb
        return self.time_at_beat(max_beat)

    @property
    def combo_count(self) -> int:
        TICKS_PER_BEAT = 480
        HALF_BEAT = TICKS_PER_BEAT // 2
        count = 0
        for note in self.notes:
            if isinstance(note, Single):
                count += 1
            elif isinstance(note, Slide):
                connections = sorted(note.connections, key=lambda c: c.beat)
                start_tick = round(connections[0].beat * TICKS_PER_BEAT)
                eighth_tick = start_tick + HALF_BEAT
                if eighth_tick % HALF_BEAT:
                    eighth_tick -= eighth_tick % HALF_BEAT
                end_tick = round(connections[-1].beat * TICKS_PER_BEAT)
                has_ticks = eighth_tick != start_tick and eighth_tick != end_tick
                prev_joint: SlideStartPoint | SlideRelayPoint | None = None
                for conn in connections:
                    if isinstance(conn, SlideStartPoint):
                        if conn.judgeType != "none":
                            count += 1
                        prev_joint = conn
                    elif isinstance(conn, SlideEndPoint):
                        if conn.judgeType != "none":
                            count += 1
                        if prev_joint is not None and has_ticks:
                            conn_tick = round(conn.beat * TICKS_PER_BEAT)
                            adj_end = conn_tick
                            if adj_end % HALF_BEAT:
                                adj_end += HALF_BEAT - adj_end % HALF_BEAT
                            if eighth_tick < adj_end:
                                steps = (adj_end - eighth_tick) // HALF_BEAT
                                count += steps
                                eighth_tick += steps * HALF_BEAT
                    elif isinstance(conn, SlideRelayPoint):
                        if conn.type == "attach":
                            if conn.critical is not None:
                                count += 1
                        else:
                            if conn.critical is not None:
                                count += 1
                            if prev_joint is not None and has_ticks:
                                conn_tick = round(conn.beat * TICKS_PER_BEAT)
                                adj_end = conn_tick
                                if adj_end % HALF_BEAT:
                                    adj_end += HALF_BEAT - adj_end % HALF_BEAT
                                if eighth_tick < adj_end:
                                    steps = (adj_end - eighth_tick) // HALF_BEAT
                                    count += steps
                                    eighth_tick += steps * HALF_BEAT
                            prev_joint = conn
        return count

    @property
    def note_count(self) -> int:
        return self.combo_count

    def _combo_before_beat(self, cutoff_beat: float) -> int:
        TICKS_PER_BEAT = 480
        HALF_BEAT = TICKS_PER_BEAT // 2
        cutoff_tick = round(cutoff_beat * TICKS_PER_BEAT)
        count = 0
        for note in self.notes:
            if isinstance(note, Single):
                if round(note.beat * TICKS_PER_BEAT) < cutoff_tick:
                    count += 1
            elif isinstance(note, Slide):
                connections = sorted(note.connections, key=lambda c: c.beat)
                start_tick = round(connections[0].beat * TICKS_PER_BEAT)
                eighth_tick = start_tick + HALF_BEAT
                if eighth_tick % HALF_BEAT:
                    eighth_tick -= eighth_tick % HALF_BEAT
                end_tick = round(connections[-1].beat * TICKS_PER_BEAT)
                has_ticks = eighth_tick != start_tick and eighth_tick != end_tick
                prev_joint: SlideStartPoint | SlideRelayPoint | None = None
                for conn in connections:
                    conn_tick = round(conn.beat * TICKS_PER_BEAT)
                    if isinstance(conn, SlideStartPoint):
                        if conn.judgeType != "none" and conn_tick < cutoff_tick:
                            count += 1
                        prev_joint = conn
                    elif isinstance(conn, SlideEndPoint):
                        if conn.judgeType != "none" and conn_tick < cutoff_tick:
                            count += 1
                        if prev_joint is not None and has_ticks:
                            adj_end = conn_tick
                            if adj_end % HALF_BEAT:
                                adj_end += HALF_BEAT - adj_end % HALF_BEAT
                            effective_end = min(adj_end, cutoff_tick)
                            if eighth_tick < effective_end:
                                steps = (
                                    effective_end - eighth_tick - 1
                                ) // HALF_BEAT + 1
                                count += steps
                                eighth_tick += steps * HALF_BEAT
                    elif isinstance(conn, SlideRelayPoint):
                        if conn.type == "attach":
                            if conn.critical is not None and conn_tick < cutoff_tick:
                                count += 1
                        else:
                            if conn.critical is not None and conn_tick < cutoff_tick:
                                count += 1
                            if prev_joint is not None and has_ticks:
                                adj_end = conn_tick
                                if adj_end % HALF_BEAT:
                                    adj_end += HALF_BEAT - adj_end % HALF_BEAT
                                effective_end = min(adj_end, cutoff_tick)
                                if eighth_tick < effective_end:
                                    steps = (
                                        effective_end - eighth_tick - 1
                                    ) // HALF_BEAT + 1
                                    count += steps
                                    eighth_tick += steps * HALF_BEAT
                            prev_joint = conn
        return count

    def cut(
        self,
        start_at: float | None = None,
        end_at: float | None = None,
        keep_position: bool = False,
    ) -> int:
        if start_at is None and end_at is None:
            raise ValueError("At least one of start_at or end_at must be specified")

        TICKS_PER_BEAT = 480

        start_beat = self.beat_at_time(start_at) if start_at is not None else 0.0
        end_beat = self.beat_at_time(end_at) if end_at is not None else float("inf")

        if start_at is not None:
            start_beat = round(start_beat * TICKS_PER_BEAT) / TICKS_PER_BEAT
        if end_at is not None:
            end_beat = round(end_beat * TICKS_PER_BEAT) / TICKS_PER_BEAT

        original_total = self.combo_count
        combo_after_raw = 0
        if end_at is not None and start_at is not None:
            end_tick = round(end_beat * TICKS_PER_BEAT)
            combo_after_raw = original_total - self._combo_before_beat(
                (end_tick + 1) / TICKS_PER_BEAT
            )

        tsg_list: list[TimeScaleGroup] = []
        for note in self.notes:
            if isinstance(note, TimeScaleGroup):
                tsg_list.append(note)

        kept: list = []
        used_tsg: set[int] = set()
        last_bpm_before: Bpm | None = None
        last_vol_before: Volume | None = None

        for note in self.notes:
            if isinstance(note, TimeScaleGroup):
                continue

            if isinstance(note, Bpm):
                if note.beat < start_beat:
                    last_bpm_before = Bpm(beat=start_beat, bpm=note.bpm)
                elif note.beat <= end_beat:
                    kept.append(note)
                continue

            if isinstance(note, Volume):
                if note.beat < start_beat:
                    last_vol_before = Volume(beat=start_beat, volume=note.volume)
                elif note.beat <= end_beat:
                    kept.append(note)
                continue

            if isinstance(note, (Skill, FeverChance, FeverStart)):
                if start_beat <= note.beat <= end_beat:
                    kept.append(note)
                continue

            if isinstance(note, Single):
                if start_beat <= note.beat <= end_beat:
                    kept.append(note)
                    used_tsg.add(note.timeScaleGroup)
                continue

            if isinstance(note, Slide):
                conns = sorted(note.connections, key=lambda c: c.beat)
                if conns[0].beat > end_beat or conns[-1].beat < start_beat:
                    continue
                if conns[0].beat >= start_beat and conns[-1].beat <= end_beat:
                    kept.append(note)
                    for c in note.connections:
                        used_tsg.add(c.timeScaleGroup)
                    continue
                result_conns: list | None = list(conns)
                if conns[0].beat < start_beat:
                    result_conns = _truncate_slide_start(
                        result_conns, start_beat, note.critical
                    )
                if result_conns and result_conns[-1].beat > end_beat:
                    result_conns = _truncate_slide_end(
                        result_conns, end_beat, note.critical
                    )
                if result_conns and len(result_conns) >= 2:
                    new_slide = Slide(
                        critical=note.critical,
                        fake=note.fake,
                        connections=result_conns,
                    )
                    kept.append(new_slide)
                    for c in result_conns:
                        used_tsg.add(c.timeScaleGroup)
                continue

            if isinstance(note, Guide):
                mps = sorted(note.midpoints, key=lambda m: m.beat)
                if mps[0].beat > end_beat or mps[-1].beat < start_beat:
                    continue
                if mps[0].beat >= start_beat and mps[-1].beat <= end_beat:
                    kept.append(note)
                    for m in note.midpoints:
                        used_tsg.add(m.timeScaleGroup)
                    continue
                result_mps: list | None = list(mps)
                if mps[0].beat < start_beat:
                    result_mps = _truncate_guide_start(result_mps, start_beat)
                if result_mps and result_mps[-1].beat > end_beat:
                    result_mps = _truncate_guide_end(result_mps, end_beat)
                if result_mps and len(result_mps) >= 2:
                    new_guide = Guide(
                        color=note.color, fade=note.fade, midpoints=result_mps
                    )
                    kept.append(new_guide)
                    for m in result_mps:
                        used_tsg.add(m.timeScaleGroup)
                continue

        if last_bpm_before is not None:
            if not any(isinstance(n, Bpm) and n.beat == start_beat for n in kept):
                kept.insert(0, last_bpm_before)

        if last_vol_before is not None:
            if not any(isinstance(n, Volume) and n.beat == start_beat for n in kept):
                kept.insert(0, last_vol_before)

        # Remove layers with no notes, renumber remaining
        old_to_new: dict[int, int] = {}
        new_tsgs: list[TimeScaleGroup] = []
        for old_idx, tsg in enumerate(tsg_list):
            if old_idx in used_tsg:
                old_to_new[old_idx] = len(new_tsgs)
                new_tsgs.append(tsg)

        for note in kept:
            if isinstance(note, Single):
                note.timeScaleGroup = old_to_new.get(note.timeScaleGroup, 0)
            elif isinstance(note, Slide):
                for conn in note.connections:
                    conn.timeScaleGroup = old_to_new.get(conn.timeScaleGroup, 0)
            elif isinstance(note, Guide):
                for mp in note.midpoints:
                    mp.timeScaleGroup = old_to_new.get(mp.timeScaleGroup, 0)

        self.notes = list(new_tsgs) + kept

        if start_at is None:
            combo_before = 0
        else:
            combo_before = original_total - self.combo_count - combo_after_raw

        if not keep_position and start_at is not None and start_beat > 0:
            shift = start_beat
            for note in self.notes:
                if isinstance(note, TimeScaleGroup):
                    trimmed: list[TimeScalePoint] = []
                    last_before: TimeScalePoint | None = None
                    for tp in note.changes:
                        if tp.beat < shift:
                            last_before = tp
                        else:
                            trimmed.append(
                                TimeScalePoint(
                                    beat=tp.beat - shift, timeScale=tp.timeScale
                                )
                            )
                    if last_before is not None and (not trimmed or trimmed[0].beat > 0):
                        trimmed.insert(
                            0,
                            TimeScalePoint(beat=0.0, timeScale=last_before.timeScale),
                        )
                    note.changes = trimmed
                elif isinstance(note, (Bpm, Volume)):
                    note.beat = max(0.0, note.beat - shift)
                elif isinstance(note, (Single, Skill, FeverChance, FeverStart)):
                    note.beat -= shift
                elif isinstance(note, Slide):
                    for conn in note.connections:
                        conn.beat -= shift
                elif isinstance(note, Guide):
                    for mp in note.midpoints:
                        mp.beat -= shift

        return combo_before
