from dataclasses import dataclass
from .metadata import MetaData
from .bpm import Bpm
from .timescale import TimeScaleGroup
from .single import Single
from .slide import Slide, SlideStartPoint, SlideRelayPoint, SlideEndPoint
from .guide import Guide, GuidePoint


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
        list[Single | SlideStartPoint | SlideRelayPoint | SlideEndPoint | GuidePoint]
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


@dataclass
class Score:
    metadata: MetaData
    notes: list[Bpm | TimeScaleGroup | Single | Slide | Guide]

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

    # 重なっているノーツをずらす
    def shift(self):
        tmp_notes = []

        # 一旦、中継点灯を含めた全部のノーツを入れたリストを作る（BPM, ソフランは除外）
        for note in self.notes:
            if isinstance(note, Bpm) or isinstance(note, TimeScaleGroup):
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
            if isinstance(note, Bpm) or isinstance(note, TimeScaleGroup):
                continue

            if isinstance(note, Single):
                _shift_single(note, split_tmp_notes)
            elif isinstance(note, Slide):
                _shift_slide(note, split_tmp_notes)
            elif isinstance(note, Guide):
                _shift_guide(note, split_tmp_notes)
