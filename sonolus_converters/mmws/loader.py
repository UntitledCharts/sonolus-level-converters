from .mmw_io import *

from typing import TextIO, Type, Iterable, TypeVar

T = TypeVar("T")


def read_metadata(fbin: BinaryIO):
    return MetaData(
        title=read_cstr(fbin, 64),
        designer=read_cstr(fbin, 64),
        artist=(read_cstr(fbin, 64), read_cstr(fbin, 64))[
            0
        ],  # artist + musicFile(read to advance buffer)
        waveoffset=read_float(fbin) / -1000,
        requests=[],
    )


def read_events(
    fbin: BinaryIO, version: Version, time_scale_groups: list[TimeScaleGroup]
):
    events: list[Bpm | Skill | FeverStart | FeverChance] = []
    time_signature_count = read_int(fbin)
    if time_signature_count:
        fbin.seek(3 * time_signature_count * (32 // 8), os.SEEK_CUR)
    tempo_count = read_int(fbin)
    for _ in range(tempo_count):
        tempo = Bpm(beat=tick_to_beat(read_int(fbin)), bpm=read_float(fbin))
        events.append(tempo)

    if version.has_hispeed:
        hispeed_count = read_int(fbin)
        for _ in range(hispeed_count):
            time_scale = TimeScalePoint(
                beat=tick_to_beat(read_int(fbin)), timeScale=read_float(fbin)
            )
            group_id = read_int(fbin) if version.has_layers else 0
            time_scale_groups[group_id].append(time_scale)

    if version.has_skill_fever:
        skill_count = read_int(fbin)
        for _ in range(skill_count):
            skill = Skill(beat=tick_to_beat(read_int(fbin)))
            events.append(skill)
        fever_chance_tick = read_int(fbin, 32, True)
        fever_start_tick = read_int(fbin, 32, True)
        if fever_chance_tick > 0:
            events.append(FeverChance(beat=tick_to_beat(fever_chance_tick)))
        if fever_start_tick > 0:
            events.append(FeverStart(beat=tick_to_beat(fever_start_tick)))
    return events


TYPE_PARAMS: dict[Type, Iterable[str]] = {
    Single: (
        "beat",
        "critical",
        "lane",
        "size",
        "fake",
        "timeScaleGroup",
        "trace",
        "direction",
    ),
    GuidePoint: ("beat", "ease", "lane", "size", "timeScaleGroup"),
    SlideStartPoint: (
        "beat",
        "critical",
        "ease",
        "judgeType",
        "lane",
        "size",
        "timeScaleGroup",
    ),
    SlideRelayPoint: (
        "beat",
        "ease",
        "lane",
        "size",
        "timeScaleGroup",
        "critical",
        "type",
    ),
    SlideEndPoint: (
        "beat",
        "critical",
        "judgeType",
        "lane",
        "size",
        "timeScaleGroup",
        "direction",
    ),
}


def data_init(data_type: Type[T], data: dict) -> T:
    return data_type(**{k: data[k] for k in TYPE_PARAMS[data_type] if k in data})


def read_note_data(
    fbin: BinaryIO, version: Version, type: Literal["tap", "start", "mid", "end"]
):
    if version.has_floatLaneWidth:
        tick = read_int(fbin)
        lane = read_float(fbin)
        width = read_float(fbin)
    else:
        tick = read_int(fbin)
        lane = read_int(fbin)
        width = read_int(fbin)
    layer = read_int(fbin) if version.has_layers else 0
    flick = read_int(fbin) if type != "start" and type != "mid" else FlickType.NONE
    flag = read_int(fbin)
    dummy = bool(flag & NoteFlag.NOTE_DUMMY) if version.has_dummyNote else False
    data = {
        "beat": tick_to_beat(tick),
        "lane": to_usc_lane(lane, width),
        "size": width_to_size(width),
        "timeScaleGroup": layer,
        "critical": bool(flag & NoteFlag.NOTE_CRITICAL),
        "trace": bool(flag & NoteFlag.NOTE_FRICTION),
        "direction": flick_to_direction(flick),
        "fake": dummy,
    }
    if flag & NoteFlag.NOTE_FRICTION:
        data["judgeType"] = "trace"
    if type == "mid":
        hold_step_type = read_int(fbin)
        match hold_step_type:
            case 0:  # Normal tick
                data["type"] = "tick"
            case 1:  # Hidden tick
                data["type"] = "tick"
                data["critical"] = None
            case 2:  # Skip tick
                data["type"] = "attach"
    if type == "start" or type == "mid":
        data["ease"] = ease_num_to_ease(read_int(fbin))
    return data


def read_taps(fbin: BinaryIO, version: Version, type: Literal["single", "damage"]):
    notes: list[Single] = []
    note_count = read_int(fbin)
    for _ in range(note_count):
        notes.append(
            data_init(Single, {"type": type, **read_note_data(fbin, version, "tap")})
        )
    return notes


def read_holds(fbin: BinaryIO, version: Version):
    holds: list[Guide | Slide] = []
    hold_count = read_int(fbin)
    for _ in range(hold_count):
        flag = read_int(fbin) if version.has_guideNote else 0
        is_guide = bool(flag & HoldFlag.HOLD_GUIDE)
        is_fake = bool(flag & HoldFlag.HOLD_FAKE)
        start_judge = "none" if flag & HoldFlag.HOLD_START_HIDDEN else "normal"
        end_judge = "none" if flag & HoldFlag.HOLD_END_HIDDEN else "normal"
        start_data = read_note_data(fbin, version, "start")
        if is_guide:
            guide_start = data_init(GuidePoint, start_data)
        else:
            hold_start = data_init(
                SlideStartPoint, {"judgeType": start_judge, **start_data}
            )

        if version.has_fadeType:
            fade_type = read_int(fbin)
        else:
            fade_type = 0  # out
        guide_color = (
            read_int(fbin)
            if version.has_guideColor
            else (GuideColor.YELLOW if start_data["critical"] else GuideColor.GREEN)
        )

        hold_step_count = read_int(fbin)
        if is_guide:
            guide = Guide(
                color=guide_color_to_color(guide_color),
                fade=fade_type_to_fade(fade_type),
                midpoints=[guide_start],
            )
            for _ in range(hold_step_count):
                guide.append(
                    data_init(GuidePoint, read_note_data(fbin, version, "mid"))
                )
            guide.append(
                data_init(
                    GuidePoint,
                    {"ease": "linear", **read_note_data(fbin, version, "end")},
                )
            )
            holds.append(guide)
        else:
            slide = Slide(
                critical=start_data["critical"], fake=is_fake, connections=[hold_start]
            )
            for _ in range(hold_step_count):
                slide.append(
                    data_init(SlideRelayPoint, read_note_data(fbin, version, "mid"))
                )
            slide.append(
                data_init(
                    SlideEndPoint,
                    {"judgeType": end_judge, **read_note_data(fbin, version, "end")},
                )
            )
            holds.append(slide)
    return holds


def load(fp: TextIO) -> Score:
    fbin = fp.buffer
    signature = read_cstr(fbin, len(Signature.MikuMikuWorld4UntitledChart.value) + 1)
    version: Version
    match signature:
        case Signature.MikuMikuWorld.value:
            version = Version(0, 0, read_int(fbin))
        case Signature.MikuMikuWorld4ChartCyanvas.value:
            version = Version(
                0, version=read_int(fbin, 16), cc_version=read_int(fbin, 16)
            )
        case Signature.MikuMikuWorld4UntitledChart.value:
            version = Version(read_int(fbin))
        case _:
            raise ValueError("Invalid MMWS file. Unrecognized signature")

    if version.has_address:
        metadata_address = read_int(fbin)
        events_address = read_int(fbin)
        tapsAddress = read_int(fbin)
        holdsAddress = read_int(fbin)
        damagesAddress = read_int(fbin) if version.has_damageNote else None
        layersAddress = read_int(fbin) if version.has_layers else None
        _ = read_int(fbin) if version.has_waypoints else None

    if version.has_address:
        fbin.seek(metadata_address, os.SEEK_SET)
    metadata = read_metadata(fbin)
    notes_data: list[
        Bpm | TimeScaleGroup | Single | Skill | FeverStart | FeverChance | Slide | Guide
    ] = []

    time_scale_groups: list[TimeScaleGroup]
    if version.has_address and layersAddress:
        fbin.seek(layersAddress, os.SEEK_SET)
        layerCount = read_int(fbin)
        time_scale_groups = [TimeScaleGroup() for _ in range(layerCount)]
    else:
        time_scale_groups = [TimeScaleGroup()]
    notes_data.extend(time_scale_groups)

    if version.has_address:
        fbin.seek(events_address, os.SEEK_SET)
    notes_data.extend(read_events(fbin, version, time_scale_groups))

    if version.has_address:
        fbin.seek(tapsAddress, os.SEEK_SET)
    notes_data.extend(read_taps(fbin, version, "single"))

    if version.has_address:
        fbin.seek(holdsAddress, os.SEEK_SET)
    notes_data.extend(read_holds(fbin, version))

    if version.has_address and damagesAddress:
        fbin.seek(damagesAddress, os.SEEK_SET)
        notes_data.extend(read_taps(fbin, version, "damage"))

    return Score(metadata=metadata, notes=notes_data)
