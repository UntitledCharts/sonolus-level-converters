import math

from pathlib import Path
import io
from typing import Union

import custom_sus_io as csus
from typing import cast
from ..version import __version__
from ..notes.score import Score
from ..notes.bpm import Bpm
from ..notes.timescale import TimeScaleGroup, TimeScalePoint
from ..notes.single import Single, Skill, FeverStart, FeverChance
from ..notes.slide import Slide, SlideStartPoint, SlideRelayPoint, SlideEndPoint
from ..notes.guide import Guide, GuidePoint
from .notetype import SusNoteType


# beatをtickに変換する
def beat_to_tick(beat: float) -> int:
    return round(480 * beat)


# uscのレーン記法からsusのレーン記法に変換する
def usc_lanes_to_sus_lanes(lane: float, size: float) -> int:
    return int(lane - size + 8)


# uscのノーツサイズ記法からsusのノーツサイズ記法に変換する
def usc_notesize_to_sus_notesize(size: float) -> int:
    # if size % 0.5 != 0:
    #    Exception("小数幅が検出されました")
    return int(math.ceil(size * 2))


def convert_tils(tils: dict[int, tuple]) -> list[tuple]:
    return [value for _, value in sorted(tils.items())]


def export(
    path: Union[str, Path, io.BytesIO, io.StringIO, io.TextIOBase],
    score: Score,
    allow_layers: bool = False,
    allow_extended_lanes: bool = False,
):
    """
    Automatically replaces extended eases and guide colors, deleting fake and damage notes.

    NOTE: also deletes extended lanes! call strip_extended_lanes with replace=True if you wish to attempt automatic replacement

    If you want to define your custom color map for replacing, run the .replace_extended_guide_colors with your own map.
    """

    def check_tsg(data_obj) -> None:
        if data_obj.timeScaleGroup != 0 and not allow_layers:
            raise ValueError(
                "Layers found (timeScaleGroup) where allow_layers is false (exporting sus)"
            )

    score.replace_extended_ease()
    score.replace_extended_guide_colors()
    score.delete_fake_notes()
    score.delete_damage_notes()
    if not allow_extended_lanes:
        score.strip_extended_lanes()
    metadata = score.metadata
    notes = score.notes
    taps = []
    directionals = []
    slides = []
    guides = []
    bpms = []
    tils = {}

    til_index = 0
    for note in notes:
        if isinstance(note, Bpm):
            tick = beat_to_tick(note.beat)
            bpms.append((tick, note.bpm))

        elif isinstance(note, TimeScaleGroup):
            note = cast(TimeScaleGroup, note)
            til = []
            if til_index != 0 and not allow_layers:
                raise ValueError(
                    "Layers found (timeScaleGroup) where allow_layers is false (exporting sus)"
                )
            for changepoint in note.changes:
                changepoint = cast(TimeScalePoint, changepoint)
                tick = beat_to_tick(changepoint.beat)
                til.append((tick, changepoint.timeScale))
            tils[til_index] = til
            til_index += 1

        elif isinstance(note, (Skill, FeverChance, FeverStart)):
            event_lane = {"skill": 0, "feverChance": 15, "feverStart": 15}
            event_tap_type = {
                "skill": SusNoteType.Tap.SKILL,
                "feverChance": SusNoteType.Tap.TAP,
                "feverStart": SusNoteType.Tap.C_TAP,
            }
            lane = usc_lanes_to_sus_lanes(event_lane[note.type], 1)
            width = usc_notesize_to_sus_notesize(1)
            tick = beat_to_tick(note.beat)
            taps.append(
                csus.Note(
                    tick=tick,
                    lane=lane,
                    width=width,
                    type=event_tap_type[note.type],
                    til=0,
                )
            )
        elif isinstance(note, Single):
            lane = usc_lanes_to_sus_lanes(note.lane, note.size)
            width = usc_notesize_to_sus_notesize(note.size)
            tick = beat_to_tick(note.beat)
            check_tsg(note)
            if note.trace:  # トレース or 金トレース
                if note.critical:
                    taps.append(
                        csus.Note(
                            tick=tick,
                            lane=lane,
                            width=width,
                            type=SusNoteType.Tap.C_TRACE,
                            til=note.timeScaleGroup,
                        )
                    )
                else:
                    taps.append(
                        csus.Note(
                            tick=tick,
                            lane=lane,
                            width=width,
                            type=SusNoteType.Tap.TRACE,
                            til=note.timeScaleGroup,
                        )
                    )
            else:  # タップ or 金タップ
                if note.critical:
                    taps.append(
                        csus.Note(
                            tick=tick,
                            lane=lane,
                            width=width,
                            type=SusNoteType.Tap.C_TAP,
                            til=note.timeScaleGroup,
                        )
                    )
                else:
                    taps.append(
                        csus.Note(
                            tick=tick,
                            lane=lane,
                            width=width,
                            type=SusNoteType.Tap.TAP,
                            til=note.timeScaleGroup,
                        )
                    )
            if note.direction:  # フリック付
                if note.direction == "up":
                    directionals.append(
                        csus.Note(
                            tick=tick,
                            lane=lane,
                            width=width,
                            type=SusNoteType.Air.UP,
                            til=note.timeScaleGroup,
                        )
                    )
                elif note.direction == "left":
                    directionals.append(
                        csus.Note(
                            tick=tick,
                            lane=lane,
                            width=width,
                            type=SusNoteType.Air.LEFT_UP,
                            til=note.timeScaleGroup,
                        )
                    )
                elif note.direction == "right":
                    directionals.append(
                        csus.Note(
                            tick=tick,
                            lane=lane,
                            width=width,
                            type=SusNoteType.Air.RIGHT_UP,
                            til=note.timeScaleGroup,
                        )
                    )

        elif isinstance(note, Slide):
            slide = []
            for step in note.connections:
                tick = beat_to_tick(step.beat)
                lane = usc_lanes_to_sus_lanes(step.lane, step.size)
                width = usc_notesize_to_sus_notesize(step.size)
                check_tsg(step)
                # 始点
                if step.type == "start":
                    step = cast(SlideStartPoint, step)
                    if step.ease == "in":  # 加速
                        directionals.append(
                            csus.Note(
                                tick=tick,
                                lane=lane,
                                width=width,
                                type=SusNoteType.Air.DOWN,
                                til=step.timeScaleGroup,
                            )
                        )
                    elif step.ease == "out":  # 減速
                        directionals.append(
                            csus.Note(
                                tick=tick,
                                lane=lane,
                                width=width,
                                type=SusNoteType.Air.RIGHT_DOWN,
                                til=step.timeScaleGroup,
                            )
                        )
                    elif step.ease == "linear":  # 直線
                        pass
                    if step.judgeType == "none":  # 始点消し
                        if step.critical:
                            taps.append(
                                csus.Note(
                                    tick=tick,
                                    lane=lane,
                                    width=width,
                                    type=SusNoteType.Tap.C_ELASER,
                                    til=step.timeScaleGroup,
                                )
                            )
                        else:
                            taps.append(
                                csus.Note(
                                    tick=tick,
                                    lane=lane,
                                    width=width,
                                    type=SusNoteType.Tap.ELASER,
                                    til=step.timeScaleGroup,
                                )
                            )
                    elif step.judgeType == "trace":  # 始点トレース
                        if step.critical:
                            taps.append(
                                csus.Note(
                                    tick=tick,
                                    lane=lane,
                                    width=width,
                                    type=SusNoteType.Tap.C_TRACE,
                                    til=step.timeScaleGroup,
                                )
                            )
                        else:
                            taps.append(
                                csus.Note(
                                    tick=tick,
                                    lane=lane,
                                    width=width,
                                    type=SusNoteType.Tap.TRACE,
                                    til=step.timeScaleGroup,
                                )
                            )
                    elif step.judgeType == "normal":
                        if step.critical:
                            taps.append(
                                csus.Note(
                                    tick=tick,
                                    lane=lane,
                                    width=width,
                                    type=SusNoteType.Tap.C_TAP,
                                    til=step.timeScaleGroup,
                                )
                            )
                    slide.append(
                        csus.Note(
                            tick=tick,
                            lane=lane,
                            width=width,
                            type=SusNoteType.Slide.START,
                            til=step.timeScaleGroup,
                        )
                    )

                # 中継点
                elif step.type in ("tick", "attach"):
                    step = cast(SlideRelayPoint, step)
                    if step.ease == "in":  # 加速
                        taps.append(
                            csus.Note(
                                tick=tick,
                                lane=lane,
                                width=width,
                                type=SusNoteType.Tap.TAP,
                                til=step.timeScaleGroup,
                            )
                        )
                        directionals.append(
                            csus.Note(
                                tick=tick,
                                lane=lane,
                                width=width,
                                type=SusNoteType.Air.DOWN,
                                til=step.timeScaleGroup,
                            )
                        )
                    elif step.ease == "out":  # 減速
                        taps.append(
                            csus.Note(
                                tick=tick,
                                lane=lane,
                                width=width,
                                type=SusNoteType.Tap.TAP,
                                til=step.timeScaleGroup,
                            )
                        )
                        directionals.append(
                            csus.Note(
                                tick=tick,
                                lane=lane,
                                width=width,
                                type=SusNoteType.Air.RIGHT_DOWN,
                                til=step.timeScaleGroup,
                            )
                        )
                    elif step.ease == "linear":  # 直線
                        pass
                    if step.type == "tick":
                        if step.critical == None:  # 不可視中継点
                            slide.append(
                                csus.Note(
                                    tick=tick,
                                    lane=lane,
                                    width=width,
                                    type=SusNoteType.Slide.STEP,
                                    til=step.timeScaleGroup,
                                )
                            )
                        else:  # 可視中継点
                            slide.append(
                                csus.Note(
                                    tick=tick,
                                    lane=lane,
                                    width=width,
                                    type=SusNoteType.Slide.VISIBLE_STEP,
                                    til=step.timeScaleGroup,
                                )
                            )
                    elif step.type == "attach":  # 無視中継点
                        taps.append(
                            csus.Note(
                                tick=tick,
                                lane=lane,
                                width=width,
                                type=SusNoteType.Tap.FLICK,
                                til=step.timeScaleGroup,
                            )
                        )
                        slide.append(
                            csus.Note(
                                tick=tick,
                                lane=lane,
                                width=width,
                                type=SusNoteType.Slide.VISIBLE_STEP,
                                til=step.timeScaleGroup,
                            )
                        )

                # 終点
                elif step.type == "end":
                    step = cast(SlideEndPoint, step)
                    if step.judgeType == "none":  # 終点消し
                        if step.critical:
                            taps.append(
                                csus.Note(
                                    tick=tick,
                                    lane=lane,
                                    width=width,
                                    type=SusNoteType.Tap.C_ELASER,
                                    til=step.timeScaleGroup,
                                )
                            )
                        else:
                            taps.append(
                                csus.Note(
                                    tick=tick,
                                    lane=lane,
                                    width=width,
                                    type=SusNoteType.Tap.ELASER,
                                    til=step.timeScaleGroup,
                                )
                            )
                    elif step.judgeType == "trace":  # 終点トレース
                        if step.critical:
                            taps.append(
                                csus.Note(
                                    tick=tick,
                                    lane=lane,
                                    width=width,
                                    type=SusNoteType.Tap.C_TRACE,
                                    til=step.timeScaleGroup,
                                )
                            )
                        else:
                            taps.append(
                                csus.Note(
                                    tick=tick,
                                    lane=lane,
                                    width=width,
                                    type=SusNoteType.Tap.TRACE,
                                    til=step.timeScaleGroup,
                                )
                            )
                    elif step.judgeType == "normal":
                        if step.direction:
                            if step.critical:
                                taps.append(
                                    csus.Note(
                                        tick=tick,
                                        lane=lane,
                                        width=width,
                                        type=SusNoteType.Tap.C_TAP,
                                        til=step.timeScaleGroup,
                                    )
                                )
                    if step.direction:  # フリック付
                        if step.direction == "up":
                            directionals.append(
                                csus.Note(
                                    tick=tick,
                                    lane=lane,
                                    width=width,
                                    type=SusNoteType.Air.UP,
                                    til=step.timeScaleGroup,
                                )
                            )
                        elif step.direction == "left":
                            directionals.append(
                                csus.Note(
                                    tick=tick,
                                    lane=lane,
                                    width=width,
                                    type=SusNoteType.Air.LEFT_UP,
                                    til=step.timeScaleGroup,
                                )
                            )
                        elif step.direction == "right":
                            directionals.append(
                                csus.Note(
                                    tick=tick,
                                    lane=lane,
                                    width=width,
                                    type=SusNoteType.Air.RIGHT_UP,
                                    til=step.timeScaleGroup,
                                )
                            )
                    slide.append(
                        csus.Note(
                            tick=tick,
                            lane=lane,
                            width=width,
                            type=SusNoteType.Slide.END,
                            til=step.timeScaleGroup,
                        )
                    )
            slides.append(slide)

        elif isinstance(note, Guide):
            guide = []
            point_length = len(note.midpoints)
            for idx, step in enumerate(note.midpoints):
                step = cast(GuidePoint, step)
                tick = beat_to_tick(step.beat)
                lane = usc_lanes_to_sus_lanes(step.lane, step.size)
                width = usc_notesize_to_sus_notesize(step.size)
                check_tsg(step)
                # 始点
                if idx == 0:
                    if note.color == "yellow":
                        taps.append(
                            csus.Note(
                                tick=tick,
                                lane=lane,
                                width=width,
                                type=SusNoteType.Tap.C_ELASER,
                                til=step.timeScaleGroup,
                            )
                        )
                    elif note.color == "green":
                        taps.append(
                            csus.Note(
                                tick=tick,
                                lane=lane,
                                width=width,
                                type=SusNoteType.Tap.ELASER,
                                til=step.timeScaleGroup,
                            )
                        )

                    if step.ease == "in":  # 加速
                        directionals.append(
                            csus.Note(
                                tick=tick,
                                lane=lane,
                                width=width,
                                type=SusNoteType.Air.DOWN,
                                til=step.timeScaleGroup,
                            )
                        )
                    elif step.ease == "out":  # 減速
                        directionals.append(
                            csus.Note(
                                tick=tick,
                                lane=lane,
                                width=width,
                                type=SusNoteType.Air.RIGHT_DOWN,
                                til=step.timeScaleGroup,
                            )
                        )
                    elif step.ease == "linear":  # 直線
                        pass
                    guide.append(
                        csus.Note(
                            tick=tick,
                            lane=lane,
                            width=width,
                            type=SusNoteType.Guide.START,
                            til=step.timeScaleGroup,
                        )
                    )

                # 終点
                elif idx == point_length - 1:
                    if note.color == "yellow":
                        taps.append(
                            csus.Note(
                                tick=tick,
                                lane=lane,
                                width=width,
                                type=SusNoteType.Tap.C_ELASER,
                                til=step.timeScaleGroup,
                            )
                        )
                    elif note.color == "green":
                        pass
                    guide.append(
                        csus.Note(
                            tick=tick,
                            lane=lane,
                            width=width,
                            type=SusNoteType.Guide.END,
                            til=step.timeScaleGroup,
                        )
                    )

                # 中継点
                else:
                    if step.ease == "in":  # 加速
                        if note.color == "yellow":
                            taps.append(
                                csus.Note(
                                    tick=tick,
                                    lane=lane,
                                    width=width,
                                    type=SusNoteType.Tap.C_ELASER,
                                    til=step.timeScaleGroup,
                                )
                            )
                        elif note.color == "green":
                            taps.append(
                                csus.Note(
                                    tick=tick,
                                    lane=lane,
                                    width=width,
                                    type=SusNoteType.Tap.ELASER,
                                    til=step.timeScaleGroup,
                                )
                            )
                        directionals.append(
                            csus.Note(
                                tick=tick,
                                lane=lane,
                                width=width,
                                type=SusNoteType.Air.DOWN,
                                til=step.timeScaleGroup,
                            )
                        )
                    elif step.ease == "out":  # 減速
                        if note.color == "yellow":
                            taps.append(
                                csus.Note(
                                    tick=tick,
                                    lane=lane,
                                    width=width,
                                    type=SusNoteType.Tap.C_ELASER,
                                    til=step.timeScaleGroup,
                                )
                            )
                        elif note.color == "green":
                            taps.append(
                                csus.Note(
                                    tick=tick,
                                    lane=lane,
                                    width=width,
                                    type=SusNoteType.Tap.ELASER,
                                    til=step.timeScaleGroup,
                                )
                            )
                        directionals.append(
                            csus.Note(
                                tick=tick,
                                lane=lane,
                                width=width,
                                type=SusNoteType.Air.RIGHT_DOWN,
                                til=step.timeScaleGroup,
                            )
                        )
                    elif step.ease == "linear":  # 直線
                        if note.color == "yellow":
                            taps.append(
                                csus.Note(
                                    tick=tick,
                                    lane=lane,
                                    width=width,
                                    type=SusNoteType.Tap.C_ELASER,
                                    til=step.timeScaleGroup,
                                )
                            )
                        elif note.color == "green":
                            pass
                    guide.append(
                        csus.Note(
                            tick=tick,
                            lane=lane,
                            width=width,
                            type=SusNoteType.Guide.STEP,
                            til=step.timeScaleGroup,
                        )
                    )
            guides.append(guide)

    if len(bpms) == 0:
        # default to 160 bpm
        # (tick 0, 160 bpm)
        bpms.append((0, 160.0))

    sus_metadata = csus.Metadata(
        title=metadata.title,
        artist=metadata.artist,
        designer=metadata.designer,
        waveoffset=-metadata.waveoffset,
        requests=metadata.requests,
    )

    sus_text = csus.dumps(
        csus.Score(
            metadata=sus_metadata,
            taps=taps,
            directionals=directionals,
            slides=slides,
            guides=guides,
            bpms=bpms,
            bar_lengths=[(0, 4.0)],
            tils=convert_tils(tils),
        ),
        comment=f"This file was generated by sonolus-level-converters {__version__}",
    )

    if isinstance(path, (str, Path)):
        path = Path(path)
        path.parent.mkdir(
            parents=True, exist_ok=True
        )  # optional: ensure directory exists
        with path.open("w", encoding="utf-8") as f:
            f.write(sus_text)
    elif isinstance(path, (io.StringIO, io.TextIOBase)):
        # file-like text object
        path.write(sus_text)
        path.seek(0)
    elif isinstance(path, io.BytesIO):
        # write UTF-8 bytes
        path.write(sus_text.encode("utf-8"))
        path.seek(0)
    else:
        raise TypeError(f"Unsupported path type: {type(path)}")
