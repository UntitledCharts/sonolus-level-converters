import custom_sus_io as csus
from typing import TextIO, Literal
from ..notes.score import Score
from ..notes.metadata import MetaData
from ..notes.bpm import Bpm
from ..notes.timescale import TimeScaleGroup, TimeScalePoint
from ..notes.single import Single, Skill, FeverChance, FeverStart
from ..notes.slide import Slide, SlideStartPoint, SlideRelayPoint, SlideEndPoint
from ..notes.guide import Guide, GuidePoint
from .notetype import SusNoteType


# tickをbeatに変換する
def _tick_to_beat(tick: int) -> float:
    return round(float(tick / 480), 6)


# susのレーン記法からuscのレーン記法に変換する
def _sus_lanes_to_usc_lanes(lane: int, width: int) -> float:
    return float(lane + (width / 2) - 8)


# susのノーツサイズ記法からuscのノーツサイズ記法に変換する
def _sus_notesize_to_usc_notesize(width: int) -> float:
    return float(width / 2)


# 同じ位置にあるノーツを探す
def _search_samepos_note(
    note_info: tuple[int, int, int], notes: list, remove: bool
) -> int | None:
    for note in notes[:]:
        if (note.tick, note.lane, note.til) == note_info:
            if remove:
                notes.remove(note)
            return note.type
    return None


# クリティカルか調べる
def _search_is_critical(tap_note: int | None) -> bool:
    if (
        tap_note == SusNoteType.Tap.C_TAP
        or tap_note == SusNoteType.Tap.C_TRACE
        or tap_note == SusNoteType.Tap.C_ELASER
    ):
        return True
    return False


# トレースか調べる
def _search_is_trace(tap_note: int | None) -> bool:
    if tap_note == SusNoteType.Tap.TRACE or tap_note == SusNoteType.Tap.C_TRACE:
        return True
    return False


# ロングの始終点のノーツを調べる
def _search_judge_type(tap_note: int | None) -> Literal["normal", "trace", "none"]:
    match tap_note:
        case SusNoteType.Tap.TRACE | SusNoteType.Tap.C_TRACE:
            return "trace"
        case SusNoteType.Tap.ELASER | SusNoteType.Tap.C_ELASER:
            return "none"
        case _:
            return "normal"


# ロング、ガイドの曲げ方を調べる
def _search_ease_type(air_note: int | None) -> Literal["in", "out", "linear"]:
    match air_note:
        case SusNoteType.Air.DOWN:
            return "in"
        case SusNoteType.Air.LEFT_DOWN | SusNoteType.Air.RIGHT_DOWN:
            return "out"
        case _:
            return "linear"


# フリックの向きを調べる
def _search_directional_type(
    air_note: int | None,
) -> Literal["left", "up", "right"] | None:
    match air_note:
        case SusNoteType.Air.UP:
            return "up"
        case SusNoteType.Air.LEFT_UP:
            return "left"
        case SusNoteType.Air.RIGHT_UP:
            return "right"
        case _:
            return None


def load(fp: TextIO) -> Score:
    sus_score = csus.load(fp)
    notes = []

    # BPM
    added_bpm = False
    for bpm in sorted(sus_score.bpms, key=lambda x: x[0]):
        notes.append(Bpm(beat=_tick_to_beat(bpm[0]), bpm=bpm[1]))
        added_bpm = True
    if not added_bpm:
        notes.append(Bpm(beat=0, bpm=160.0))

    # ハイスピ
    exist_initial_time_scale = False
    time_scale_group = TimeScaleGroup()
    for til in sus_score.tils:
        for change in sorted(til, key=lambda x: x[0]):
            if change[0] == 0:
                exist_initial_time_scale = True
            time_scale_group.append(
                TimeScalePoint(beat=_tick_to_beat(til[0]), timeScale=til[1])
            )
    if not exist_initial_time_scale:
        time_scale_group.insert(0, TimeScalePoint(beat=0.0, timeScale=1.0))
    notes.append(time_scale_group)

    # スライド
    for slide in sus_score.slides:
        point_length = len(slide)
        slide_note = Slide(critical=False)
        for idx, point in zip(range(point_length), sorted(slide, key=lambda x: x.tick)):
            samepos_tap = _search_samepos_note(
                (point.tick, point.lane, point.til), sus_score.taps, remove=True
            )
            samepos_direction = _search_samepos_note(
                (point.tick, point.lane, point.til), sus_score.directionals, remove=True
            )
            critical = _search_is_critical(samepos_tap)
            judge_type = _search_judge_type(samepos_tap)
            ease = _search_ease_type(samepos_direction)
            direction = _search_directional_type(samepos_direction)
            beat = _tick_to_beat(point.tick)
            lane = _sus_lanes_to_usc_lanes(point.lane, point.width)
            size = _sus_notesize_to_usc_notesize(point.width)

            if idx == 0:  # 始点
                slide_note.critical = critical
                slide_note.append(
                    SlideStartPoint(
                        beat=beat,
                        critical=critical,
                        ease=ease,
                        judgeType=judge_type,
                        lane=lane,
                        size=size,
                        timeScaleGroup=point.til,
                    )
                )
            elif idx == point_length - 1:  # 終点
                # if the slide note is critical
                # the end note is ALSO critical
                # unless specified by samepos_tap == n
                # a normal sus file will usually never specify as a TAP of the other kind; it might not even be supported.
                # however, it can specify as a non-critical or critical trace/flick regardless of hold type
                if slide_note.critical and samepos_tap == None:
                    critical = True
                slide_note.append(
                    SlideEndPoint(
                        beat=beat,
                        critical=critical,
                        judgeType=judge_type,
                        lane=lane,
                        size=size,
                        timeScaleGroup=point.til,
                        direction=direction,
                    )
                )
            else:  # 中継点
                relay_point = SlideRelayPoint(
                    beat=beat,
                    ease=ease,
                    lane=lane,
                    size=size,
                    timeScaleGroup=point.til,
                    type="tick",
                    critical=slide_note.critical,
                )
                if point.type == SusNoteType.Slide.VISIBLE_STEP:
                    if samepos_tap == SusNoteType.Tap.FLICK:
                        relay_point.type = "attach"

                elif point.type == SusNoteType.Slide.STEP:
                    relay_point.critical = None
                slide_note.append(relay_point)

        notes.append(slide_note)

    # ガイド
    for guide in sus_score.guides:
        point_length = len(guide)
        guide_note = Guide(color="green", fade="out")
        for idx, point in zip(range(point_length), sorted(guide, key=lambda x: x.tick)):
            samepos_tap = _search_samepos_note(
                (point.tick, point.lane, point.til), sus_score.taps, remove=True
            )
            samepos_direction = _search_samepos_note(
                (point.tick, point.lane, point.til), sus_score.directionals, remove=True
            )
            critical = _search_is_critical(samepos_tap)
            judge_type = _search_judge_type(samepos_tap)
            ease = _search_ease_type(samepos_direction)
            beat = _tick_to_beat(point.tick)
            lane = _sus_lanes_to_usc_lanes(point.lane, point.width)
            size = _sus_notesize_to_usc_notesize(point.width)

            if idx == 0:  # 始点
                if critical:
                    guide_note.color = "yellow"
            guide_note.append(
                GuidePoint(
                    beat=beat, ease=ease, lane=lane, size=size, timeScaleGroup=point.til
                )
            )
        notes.append(guide_note)

    # タップ、フリック系
    fever_chance = None
    fever_start = None
    for note in sorted(sus_score.taps, key=lambda x: x.tick):
        if (
            note.type == SusNoteType.Tap.SKILL and note.width == 1 and note.lane == 0
        ):  # (4) SKILL ACTIVATIONS (or damage notes in Chunithm)
            notes.append(Skill(beat=_tick_to_beat(note.tick)))
            continue
        elif note.type == SusNoteType.Tap.SKILL:
            continue  # what's that doing there?
        # fever start/end events
        if (
            note.lane == 15
            and note.width == 1
            and note.type in [SusNoteType.Tap.TAP, SusNoteType.Tap.C_TAP]
        ):
            if note.type == SusNoteType.Tap.TAP:
                if fever_chance:
                    raise AttributeError("Can only have 1 fever chance per chart.")
                notes.append(FeverChance(beat=_tick_to_beat(note.tick)))
                fever_chance = _tick_to_beat(note.tick)
            else:
                if fever_start:
                    raise AttributeError(
                        "Can only have 1 fever start (end of chance) per chart."
                    )
                notes.append(FeverStart(beat=_tick_to_beat(note.tick)))
                fever_start = _tick_to_beat(note.tick)
                if fever_start < fever_chance:
                    raise AttributeError("Fever end must be after fever start.")
            continue  # don't load them
        samepos_direction = _search_samepos_note(
            (note.tick, note.lane), sus_score.directionals, remove=True
        )
        beat = _tick_to_beat(note.tick)
        critical = _search_is_critical(note.type)
        lane = _sus_lanes_to_usc_lanes(note.lane, note.width)
        size = _sus_notesize_to_usc_notesize(note.width)
        trace = _search_is_trace(note.type)
        direction = _search_directional_type(samepos_direction)

        notes.append(
            Single(
                beat=beat,
                critical=critical,
                lane=lane,
                size=size,
                timeScaleGroup=point.til,
                trace=trace,
                direction=direction,
            )
        )
    if fever_chance and not fever_start:
        raise AttributeError("Must have a fever start if a fever chance is defined.")
    if fever_start and not fever_chance:
        raise AttributeError("Must have a fever chance if a fever start is defined.")
    notes.sort(key=lambda x: x.get_sus_sort_number())

    metadata = MetaData(
        title=sus_score.metadata.title,
        artist=sus_score.metadata.artist,
        designer=sus_score.metadata.designer,
        waveoffset=-sus_score.metadata.waveoffset,
        requests=sus_score.metadata.requests,
    )

    return Score(metadata, notes)
