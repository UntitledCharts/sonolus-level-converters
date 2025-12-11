from ..notes import *
from .mmw_io import *

from typing import Literal, Union, BinaryIO, Any, cast, overload
from pathlib import Path
import math
import io

def usc_object_get_max_lane_offset(value: Any):
    if hasattr(value, 'lane') and hasattr(value, 'size'):
        lane = float(value.lane)
        size = float(value.size)
        return max((lane + size if lane > 0 else -(lane - size)) - 6, 0)
    else:
        return 0

def write_metadata(fbin: BinaryIO, version: Version, metadata: MetaData, notes: list[Any] = []):
    write_cstr(fbin, metadata.title)
    write_cstr(fbin, metadata.designer)
    write_cstr(fbin, metadata.artist)
    write_cstr(fbin, '') # musicFile
    write_float(fbin, metadata.waveoffset * -1000)
    if version.has_jacket:
        write_cstr(fbin, '') # jacketFile
    if version.has_laneExtension:
        lane_extension = math.ceil(max(usc_object_get_max_lane_offset(note) for note in notes))
        write_int(fbin, int(lane_extension))

def write_events(fbin: BinaryIO, version: Version, noteGroup: NoteGroups):
    # Timesignature count
    write_int(fbin, 0) # Should be fine to set it to 0

    bpmChanges = noteGroup.by(Bpm)
    write_int(fbin, len(bpmChanges))
    for bpmChange in bpmChanges:
        write_int(fbin, beat_to_tick(bpmChange.beat))
        write_float(fbin, bpmChange.bpm)

    if version.has_hispeed:
        groups = noteGroup.by(TimeScaleGroup)
        time_scale_count = sum(len(group.changes) for group in groups) if version.has_layers else len(groups[0].changes)
        write_int(fbin, time_scale_count)
        for layer, group in enumerate(groups):
            for speedChange in group.changes:
                write_int(fbin, beat_to_tick(speedChange.beat))
                write_float(fbin, speedChange.timeScale)
                if version.has_layers:
                    write_int(fbin, layer)
            if not version.has_layers:
                break

    if version.has_skill_fever:
        skills = noteGroup.by(Skill)
        write_int(fbin, len(skills))
        for skill in skills:
            write_int(fbin, beat_to_tick(skill.beat))
        fever_chances = noteGroup.by(FeverChance)
        fever_starts = noteGroup.by(FeverStart)
        if len(fever_chances) == 1 and len(fever_starts) == 1:
            fever_chance_tick = beat_to_tick(fever_chances[0].beat)
            fever_start_tick = beat_to_tick(fever_starts[0].beat)
        else:
            fever_chance_tick = -1
            fever_start_tick = -1
        write_int(fbin, fever_chance_tick, 32, True)
        write_int(fbin, fever_start_tick, 32, True)

@overload
def write_note_data(fbin: BinaryIO, version: Version, note: Single, note_type: Literal['tap']): ...
@overload
def write_note_data(fbin: BinaryIO, version: Version, note: SlideStartPoint, note_type: Literal['start']): ...
@overload
def write_note_data(fbin: BinaryIO, version: Version, note: SlideRelayPoint, note_type: Literal['mid'], *, slide: Slide | None = None): ...
@overload
def write_note_data(fbin: BinaryIO, version: Version, note: SlideEndPoint, note_type: Literal['end']): ...
@overload
def write_note_data(fbin: BinaryIO, version: Version, note: GuidePoint, note_type: Literal['start', 'mid', 'end']): ...

def write_note_data(fbin: BinaryIO, version: Version, note: Single | SlideStartPoint | SlideRelayPoint | SlideEndPoint | GuidePoint, note_type: str, *, slide: Slide | None = None):
    if version.has_floatLaneWidth:
        write_int(fbin, beat_to_tick(note.beat))
        write_float(fbin, to_mmw_lane(note.lane, note.size))
        write_float(fbin, size_to_width(note.size))
    else:
        write_int(fbin, beat_to_tick(note.beat))
        write_int(fbin, to_mmw_lane(note.lane, note.size, lambda x: int(round(x))))
        write_int(fbin, size_to_width(note.size, lambda x: int(round(x))))
    if version.has_layers:
        write_int(fbin, note.timeScaleGroup)
    if note_type == 'tap' or note_type == 'end':
        direction = getattr(note, 'direction', None)
        write_int(fbin, direction_to_flick(direction))
    flag = NoteFlag.NONE
    if getattr(note, 'fake', False):
        flag |= NoteFlag.NOTE_DUMMY
    if getattr(note, 'judgeType', 'normal') == 'trace':
        flag |= NoteFlag.NOTE_FRICTION
    if getattr(note, 'critical', False) or (note_type == 'mid' and slide and slide.critical):
        flag |= NoteFlag.NOTE_CRITICAL
    write_int(fbin, flag.value)
    if note_type == 'mid':
        if isinstance(note, GuidePoint):
            write_int(fbin, 0) # Hold point
        elif note.type == 'tick':
            if note.critical is None:
                write_int(fbin, 1)
            else:
                write_int(fbin, 0)
        elif note.type == 'attach':
            write_int(fbin, 2)
        else:
            raise ValueError(f'Invalid hold mid type {note.type}')
    if note_type == 'start' or note_type == 'mid':
        write_int(fbin, ease_to_ease_num(getattr(note, 'ease', 'linear')))

def write_taps(fbin: BinaryIO, version: Version, type: Literal['single', 'damage'], noteGroup: NoteGroups):
    notes = [note for note in noteGroup.by(Single) if note.type == type]
    write_int(fbin, len(notes))
    for note in notes:
        write_note_data(fbin, version, note, 'tap')

def write_holds(fbin: BinaryIO, version: Version, noteGroup: NoteGroups):
    slides = noteGroup.by(Slide)
    guides = noteGroup.by(Guide)
    write_int(fbin, len(slides) + len(guides))
    for slide in slides:
        startHold = cast(SlideStartPoint, slide.connections[0])
        endHold = cast(SlideEndPoint, slide.connections[-1])
        holdSteps = cast(list[SlideRelayPoint], slide.connections[1:-1])
        flag: HoldFlag = HoldFlag.NONE
        if startHold.judgeType == 'none':
            flag |= HoldFlag.HOLD_START_HIDDEN
        if endHold.judgeType == 'none':
            flag |= HoldFlag.HOLD_END_HIDDEN
        if slide.fake:
            flag |= HoldFlag.HOLD_FAKE
        write_int(fbin, flag.value)
        write_note_data(fbin, version, startHold, 'start')

        if version.has_fadeType:
            write_int(fbin, FadeType.OUT.value)
        if version.has_guideColor:
            write_int(fbin, GuideColor.GREEN.value)
        
        write_int(fbin, len(holdSteps))
        for step in holdSteps:
            write_note_data(fbin, version, step, 'mid', slide=slide)
        write_note_data(fbin, version, endHold, 'end')
    for guide in guides:
        startGuide = guide.midpoints[0]
        guidePoints = guide.midpoints[1:]
        write_int(fbin, HoldFlag.HOLD_GUIDE.value)
        write_note_data(fbin, version, startGuide, 'start')

        if version.has_fadeType:
            write_int(fbin, fade_to_fade_type(guide.fade))
        if version.has_guideColor:
            write_int(fbin, color_to_guide_color(guide.color))
        
        write_int(fbin, len(guidePoints) - 1)
        for i, point in enumerate(guidePoints):
            write_note_data(fbin, version, point, 'mid' if i == (len(guidePoints) - 1) else 'end')

def export(path: Union[str, Path, io.BytesIO], score: Score, *, format: Literal['.mmws', '.ccmmws', '.unchmmws'] | str | None = None):
    if isinstance(path, io.BytesIO):
        has_path = False
        fbin = path
    elif isinstance(path, (str, Path)):
        has_path = True
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fbin = path.open("wb")
        if format is None:
            _, format = os.path.splitext(path.name)
    else:
        raise TypeError(f"Unsupported path type: {type(path)}")

    match format:
        case '.mmws':
            version = Version(0, 0)
            signature = Signature.MikuMikuWorld
            score.replace_extended_ease()
            score.replace_extended_guide_colors()
            score.delete_fake_notes()
            score.delete_damage_notes()
            score.strip_extended_lanes()
        case '.ccmmws':
            version = Version(0)
            signature = Signature.MikuMikuWorld4ChartCyanvas
            score.delete_fake_notes()
        case '.unchmmws':
            version = Version()
            signature = Signature.MikuMikuWorld4UntitledChart
        case _: raise ValueError(f'Unsupported format: {format}')
    noteGroups = NoteGroups(score.notes)

    try:
        write_cstr(fbin, signature.value)
        write_int(fbin, version.value)

        if version.has_address:
            address_size = 4 * (4 + version.has_damageNote + version.has_layers + version.has_waypoints)
            table_address = fbin.tell()
            fill_zero(fbin, address_size)

        if version.has_address:
            metadata_address = fbin.tell()
        write_metadata(fbin, version, score.metadata, score.notes)

        if version.has_address:
            events_address = fbin.tell()
        write_events(fbin, version, noteGroups)

        if version.has_address:
            tapsAddress = fbin.tell()
        write_taps(fbin, version, 'single', noteGroups)

        if version.has_address:
            holdsAddress = fbin.tell()
        write_holds(fbin, version, noteGroups)

        if version.has_address and version.has_damageNote:
            damagesAddress = fbin.tell()
            write_taps(fbin, version, 'damage', noteGroups)

        if version.has_address and version.has_layers:
            layersAddress = fbin.tell()
            layers = noteGroups.by(TimeScaleGroup)
            write_int(fbin, len(layers))
            for i in range(len(layers)):
                write_cstr(fbin, f'#{i + 1}')

        if version.has_address and version.has_waypoints:
            waypointAddress = fbin.tell()
            write_int(fbin, 0) # waypoint count

        if version.has_address:
            fbin.seek(table_address, os.SEEK_SET)
            write_int(fbin, metadata_address)
            write_int(fbin, events_address)
            write_int(fbin, tapsAddress)
            write_int(fbin, holdsAddress)
            if version.has_damageNote:
                write_int(fbin, damagesAddress)
            if version.has_layers:
                write_int(fbin, layersAddress)
            if version.has_waypoints:
                write_int(fbin, waypointAddress)
    finally:
        if has_path:
            fbin.close()
