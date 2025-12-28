from dataclasses import dataclass, asdict
from .metadata import MetaData, validate_metadata_dict_values
from .bpm import Bpm, validate_bpm_dict_values
from .timescale import TimeScaleGroup, validate_timescale_dict_values
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
        Bpm | TimeScaleGroup | Single | Skill | FeverStart | FeverChance | Slide | Guide
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
                or isinstance(note, (Skill, FeverStart, FeverChance))
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
                or isinstance(note, (Skill, FeverStart, FeverChance))
            ):
                useful_notes.append(note)
                continue
            tmp_notes.append(note)
        tmp_notes = _convert_tmp_notes(tmp_notes)

        used = {}
        added_used = []
        overlaps_at = []
        for note in tmp_notes:
            if (note.beat, note.lane) in used.keys():
                if (note.beat, note.lane) not in added_used:
                    added_used.append((note.beat, note.lane))
                    overlaps_at.append(used[(note.beat, note.lane)])
                overlaps_at.append(
                    (note.beat, note.lane, note.size, note.timeScaleGroup)
                )
            else:
                used[(note.beat, note.lane)] = (
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

        # 一旦、中継点灯を含めた全部のノーツを入れたリストを作る（BPM, ソフランは除外）
        for note in self.notes:
            if (
                isinstance(note, Bpm)
                or isinstance(note, TimeScaleGroup)
                or isinstance(note, (Skill, FeverStart, FeverChance))
            ):
                continue
            tmp_notes.append(note)
        tmp_notes = _convert_tmp_notes(tmp_notes)

        # BAR_INTERVALの小節長で分割したリストを作成するために、リストをいくつ作るか計算する
        max_beat = max(tmp_notes, key=lambda x: x.beat).beat

        # BAR_INTERVALの小節長で分割したリストを作成する
        print(max_beat // BAR_INTERVAL)
        split_tmp_notes = [list() for _ in range(int(max_beat // BAR_INTERVAL + 1))]

        # note.beatの値に対応するリストにノーツを入れる
        for note in tmp_notes:
            split_tmp_notes[_calc_notelist_index(note)].append(note)

        for note in self.notes:
            if (
                isinstance(note, Bpm)
                or isinstance(note, TimeScaleGroup)
                or isinstance(note, (Skill, FeverStart, FeverChance))
            ):
                continue

            if isinstance(note, Single):
                _shift_single(note, split_tmp_notes)
            elif isinstance(note, Slide):
                _shift_slide(note, split_tmp_notes)
            elif isinstance(note, Guide):
                _shift_guide(note, split_tmp_notes)
