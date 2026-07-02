from typing import TextIO, Literal
from ..notes.score import Score
from ..notes.metadata import MetaData
from ..notes.bpm import Bpm
from ..notes.timescale import TimeScaleGroup, TimeScalePoint
from ..notes.single import Single
from ..notes.slide import Slide, SlideStartPoint, SlideRelayPoint, SlideEndPoint
from ..sus.loader import (
    _SusNote,
    _get_bars,
    _get_ticks,
    _get_notes,
    _get_note_stream,
    _parse_hispeed_entry,
    _is_command,
    _tick_to_beat,
    _note_key,
    TICKS_PER_BEAT,
)

MIN_LANE = 2
DEFAULT_LANECOUNT = 12


def _to_usc_lane(lane: int, width: int, center: float, lane_factor: float) -> float:
    return round((lane + width / 2.0 - center) * lane_factor, 6)


def _to_usc_size(width: int, lane_factor: float) -> float:
    return round(width * lane_factor / 2.0, 6)


def load(fp: TextIO) -> Score:
    return loads(fp.read())


def loads(data: str) -> Score:
    ticks_per_beat = TICKS_PER_BEAT
    lanecount = DEFAULT_LANECOUNT
    title = ""
    artist = ""
    designer = ""
    wave_offset = 0.0
    requests: list[str] = []

    bar_lengths: list[tuple[int, float]] = []
    bpm_definitions: dict[str, float] = {}
    bpm_data_lines: list[tuple[int, float]] = []
    til_map: dict[str, int] = {}
    tils: list[list[tuple[int, float]]] = []
    til_data_index = 0
    current_til: int = 0

    taps: list[_SusNote] = []
    directionals: list[_SusNote] = []
    slide_streams: dict[int, list[_SusNote]] = {}

    # PHASE 1: bar_lengths, ticks_per_beat, MEASUREBS, LANECOUNT
    measure_offset = 0
    lines_to_process: list[tuple[str, int]] = []
    for raw_line in data.splitlines():
        line = raw_line.strip()
        if not line.startswith("#"):
            continue

        if _is_command(line):
            space = line.find(" ", 1)
            if space == -1:
                lines_to_process.append((line, measure_offset))
                continue
            key = line[1:space].upper()
            value = line[space + 1 :].strip()
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            if key == "REQUEST":
                parts = value.split()
                if len(parts) == 2 and parts[0] == "ticks_per_beat":
                    ticks_per_beat = int(parts[1])
            elif key == "MEASUREBS":
                measure_offset = int(value)
            elif key == "LANECOUNT":
                lanecount = int(value)
        else:
            colon = line.find(":", 1)
            if colon == -1:
                lines_to_process.append((line, measure_offset))
                continue
            header = line[1:colon].strip()
            line_data = line[colon + 1 :].strip()
            if len(header) == 5 and header.endswith("02") and header[:3].isdigit():
                bar_lengths.append((int(header[:3]) + measure_offset, float(line_data)))

        lines_to_process.append((line, measure_offset))

    if not bar_lengths:
        bar_lengths.append((0, 4.0))

    bars = _get_bars(bar_lengths, ticks_per_beat)

    # Lane conversion factors based on LANECOUNT
    # center = midpoint of playable area in SUS lane units
    # lane_factor = scale to normalize to 12-lane-equivalent coordinates
    lane_factor = 12.0 / lanecount
    center = MIN_LANE + lanecount / 2.0

    # PHASE 2: notes, BPM, TIL, metadata
    for line, m_offset in lines_to_process:
        if _is_command(line):
            space = line.find(" ", 1)
            if space == -1:
                continue
            key = line[1:space].upper()
            value = line[space + 1 :].strip()
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]

            if key == "TITLE":
                title = value
            elif key == "ARTIST":
                artist = value
            elif key == "DESIGNER":
                designer = value
            elif key == "WAVEOFFSET":
                wave_offset = float(value)
            elif key == "REQUEST":
                requests.append(value)
            elif key == "HISPEED":
                tid = til_map.get(value)
                if tid is not None:
                    current_til = tid
            continue

        colon = line.find(":", 1)
        if colon == -1:
            continue
        header = line[1:colon].strip()
        line_data = line[colon + 1 :].strip()

        if len(header) not in (5, 6):
            continue

        if len(header) == 5 and header.endswith("02") and header[:3].isdigit():
            pass
        elif header.startswith("BPM") and len(header) == 5:
            bpm_definitions[header[3:]] = float(line_data)
        elif len(header) == 5 and header.endswith("08"):
            measure = int(header[:3]) + m_offset
            stripped = line_data.replace(" ", "")
            pairs = [
                stripped[j : j + 2]
                for j in range(0, len(stripped) - len(stripped) % 2, 2)
            ]
            for j, pair in enumerate(pairs):
                if pair == "00":
                    continue
                tick = _get_ticks(bars, measure, j, len(pairs))
                bpm = bpm_definitions.get(pair, 120.0)
                bpm_data_lines.append((tick, bpm))
        elif header.startswith("TIL") and len(header) == 5:
            til_id = header[3:]
            til_map[til_id] = til_data_index
            stripped = line_data.strip('"').replace(" ", "")
            new_til: list[tuple[int, float]] = []
            for entry_str in stripped.split(","):
                parsed = _parse_hispeed_entry(entry_str)
                if parsed:
                    measure, tick_offset, value = parsed
                    measure_ticks = _get_ticks(bars, measure, 0, 1)
                    new_til.append((measure_ticks + tick_offset, value))
            tils.append(new_til)
            til_data_index += 1
        elif len(header) == 5 and header[3] == "1":
            measure = int(header[:3]) + m_offset
            taps.extend(_get_notes(header, line_data, bars, measure, current_til))
        elif len(header) == 5 and header[3] == "5":
            measure = int(header[:3]) + m_offset
            directionals.extend(
                _get_notes(header, line_data, bars, measure, current_til)
            )
        elif len(header) == 6 and header[3] == "3":
            measure = int(header[:3]) + m_offset
            channel = int(header[5], 36)
            slide_streams.setdefault(channel, []).extend(
                _get_notes(header, line_data, bars, measure, current_til)
            )

    slides: list[list[_SusNote]] = []
    for stream in slide_streams.values():
        slides.extend(_get_note_stream(stream))

    # Deduplicate slides sharing same start+end position
    seen: set[tuple[int, int, int, int]] = set()
    deduped: list[list[_SusNote]] = []
    for hold in slides:
        if len(hold) < 2:
            continue
        key = (hold[0].tick, hold[0].lane, hold[-1].tick, hold[-1].lane)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(hold)
    slides = deduped

    return _bandori_to_score(
        taps,
        directionals,
        slides,
        sorted(bpm_data_lines, key=lambda x: x[0]),
        tils,
        title,
        artist,
        designer,
        wave_offset,
        requests,
        lane_factor,
        center,
        lanecount,
    )


def _bandori_to_score(
    sus_taps: list[_SusNote],
    sus_directionals: list[_SusNote],
    sus_slides: list[list[_SusNote]],
    sus_bpms: list[tuple[int, float]],
    tils: list[list[tuple[int, float]]],
    title: str,
    artist: str,
    designer: str,
    wave_offset: float,
    requests: list[str],
    lane_factor: float,
    center: float,
    lanecount: int,
) -> Score:
    max_lane = MIN_LANE + lanecount - 1

    # Lookup sets (bandori has no critical/friction/hidden/trace)
    flicks: dict[str, Literal["up", "left", "right"]] = {}
    ease_ins: set[str] = set()
    ease_outs: set[str] = set()
    slide_keys: set[str] = set()

    for d in sus_directionals:
        key = _note_key(d.tick, d.lane)
        if d.type == 1:
            flicks[key] = "up"
        elif d.type == 3:
            flicks[key] = "left"
        elif d.type == 4:
            flicks[key] = "right"
        elif d.type == 2:
            ease_ins.add(key)
        elif d.type in (5, 6):
            ease_outs.add(key)

    for slide in sus_slides:
        for note in slide:
            if note.type in (1, 2, 3, 5):
                slide_keys.add(_note_key(note.tick, note.lane))

    notes: list = []

    # BPM
    if sus_bpms:
        for tick, bpm in sus_bpms:
            notes.append(Bpm(beat=_tick_to_beat(tick), bpm=bpm))
    else:
        notes.append(Bpm(beat=0, bpm=120.0))

    # TimeScale (TIL layers)
    if tils:
        for til in tils:
            tsg = TimeScaleGroup()
            has_initial = False
            for tick, speed in sorted(til, key=lambda x: x[0]):
                if tick == 0:
                    has_initial = True
                tsg.append(TimeScalePoint(beat=_tick_to_beat(tick), timeScale=speed))
            if not has_initial:
                tsg.insert(0, TimeScalePoint(beat=0.0, timeScale=1.0))
            notes.append(tsg)
    else:
        tsg = TimeScaleGroup()
        tsg.append(TimeScalePoint(beat=0.0, timeScale=1.0))
        notes.append(tsg)

    # Taps → Singles (no critical, no friction/trace in bandori)
    seen_tap_keys: set[str] = set()
    for note in sorted(sus_taps, key=lambda x: x.tick):
        if note.lane < MIN_LANE or note.lane > max_lane:
            continue

        key = _note_key(note.tick, note.lane)
        if key in slide_keys:
            continue
        if key in seen_tap_keys:
            continue
        seen_tap_keys.add(key)

        direction = flicks.get(key)
        notes.append(
            Single(
                beat=_tick_to_beat(note.tick),
                critical=False,
                lane=_to_usc_lane(note.lane, note.width, center, lane_factor),
                size=_to_usc_size(note.width, lane_factor),
                timeScaleGroup=note.til,
                speedRatio=note.speedRatio,
                trace=False,
                direction=direction,
            )
        )

    # Slides (no critical, no friction/hidden starts in bandori)
    for hold in sus_slides:
        if len(hold) < 2:
            continue

        slide_note = Slide(critical=False)
        for note in hold:
            key = _note_key(note.tick, note.lane)
            ease: Literal["in", "out", "linear"] = "linear"
            if key in ease_ins:
                ease = "in"
            elif key in ease_outs:
                ease = "out"
            beat = _tick_to_beat(note.tick)
            lane = _to_usc_lane(note.lane, note.width, center, lane_factor)
            size = _to_usc_size(note.width, lane_factor)

            if note.type == 1:
                slide_note.append(
                    SlideStartPoint(
                        beat=beat,
                        critical=False,
                        ease=ease,
                        judgeType="normal",
                        lane=lane,
                        size=size,
                        timeScaleGroup=note.til,
                        speedRatio=note.speedRatio,
                    )
                )
            elif note.type == 2:
                direction = flicks.get(key)
                slide_note.append(
                    SlideEndPoint(
                        beat=beat,
                        critical=False,
                        judgeType="normal",
                        lane=lane,
                        size=size,
                        timeScaleGroup=note.til,
                        speedRatio=note.speedRatio,
                        direction=direction,
                    )
                )
            elif note.type in (3, 5):
                # type 3 = visible relay, type 5 = invisible relay
                mid_critical: bool | None = False
                if note.type == 5:
                    mid_critical = None
                slide_note.append(
                    SlideRelayPoint(
                        beat=beat,
                        ease=ease,
                        lane=lane,
                        size=size,
                        timeScaleGroup=note.til,
                        type="tick",
                        critical=mid_critical,
                        speedRatio=note.speedRatio,
                    )
                )

        notes.append(slide_note)

    notes.sort(key=lambda x: x.get_sus_sort_number())

    metadata = MetaData(
        title=title,
        artist=artist,
        designer=designer,
        waveoffset=-wave_offset,
        requests=requests if requests else None,
    )

    return Score(metadata, notes)
