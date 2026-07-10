from typing import TextIO, Literal
from dataclasses import dataclass
from ..notes.score import Score
from ..notes.metadata import MetaData
from ..notes.bpm import Bpm
from ..notes.timescale import TimeScaleGroup, TimeScalePoint
from ..notes.single import Single, Skill, FeverChance, FeverStart
from ..notes.slide import Slide, SlideStartPoint, SlideRelayPoint, SlideEndPoint
from ..notes.guide import Guide, GuidePoint
from ..notes.volume import Volume

TICKS_PER_BEAT = 480
MIN_LANE = 2
MAX_LANE = 13
FEVER_LANE = 15


@dataclass
class _SusNote:
    tick: int
    lane: int
    width: int
    type: int
    til: int = 0
    speedRatio: float = 1.0


@dataclass
class _Bar:
    measure: int
    ticks_per_measure: int
    ticks: int


def _tick_to_beat(tick: int) -> float:
    return round(float(tick / TICKS_PER_BEAT), 6)


def _sus_to_usc_lane(lane: int, width: int) -> float:
    return float(lane + width / 2 - 8)


def _sus_to_usc_size(width: int) -> float:
    return float(width / 2)


def _note_key(tick: int, lane: int) -> str:
    return f"{tick}-{lane}"


# SUS PARSING


def _get_bars(bar_lengths: list[tuple[int, float]], ticks_per_beat: int) -> list[_Bar]:
    if not bar_lengths:
        bar_lengths = [(0, 4.0)]
    sorted_bl = sorted(bar_lengths, key=lambda x: x[0])
    bars = [_Bar(sorted_bl[0][0], int(sorted_bl[0][1] * ticks_per_beat), 0)]
    for i in range(1, len(sorted_bl)):
        measure = sorted_bl[i][0]
        tpm = int(sorted_bl[i][1] * ticks_per_beat)
        ticks = int(
            (measure - sorted_bl[i - 1][0]) * sorted_bl[i - 1][1] * ticks_per_beat
        )
        bars.append(_Bar(measure, tpm, ticks))
    return bars


def _get_ticks(bars: list[_Bar], measure: int, i: int, total: int) -> int:
    b_index = 0
    acc_ticks = 0
    for idx in range(len(bars)):
        if bars[idx].measure > measure:
            break
        b_index = idx
        acc_ticks += bars[idx].ticks
    return (
        acc_ticks
        + (measure - bars[b_index].measure) * bars[b_index].ticks_per_measure
        + (i * bars[b_index].ticks_per_measure) // total
    )


def _parse_note_cells(data: str) -> list[tuple[str, float]]:
    if "," not in data:
        end = len(data) - len(data) % 2
        return [(data[i : i + 2], 1.0) for i in range(0, end, 2)]

    cells: list[tuple[str, float]] = []
    i = 0
    while i < len(data):
        while i < len(data) and data[i].isspace():
            i += 1
        if i + 1 >= len(data):
            break
        note_data = data[i : i + 2]
        i += 2
        speed_ratio = 1.0
        if i < len(data) and data[i] == ",":
            i += 1
            start = i
            while i < len(data) and not data[i].isspace() and data[i] != ",":
                i += 1
            if i > start:
                sr = float(data[start:i])
                if sr > 0.0:
                    speed_ratio = sr
        cells.append((note_data, speed_ratio))
        while i < len(data) and (data[i].isspace() or data[i] == ","):
            i += 1
    return cells


def _get_notes(
    header: str,
    data: str,
    bars: list[_Bar],
    measure: int,
    til: int,
) -> list[_SusNote]:
    notes: list[_SusNote] = []
    cells = _parse_note_cells(data)
    for i, (cell, speed) in enumerate(cells):
        if len(cell) < 2 or cell == "00":
            continue
        tick = _get_ticks(bars, measure, i * 2, len(cells) * 2)
        lane = int(header[4], 36)
        width = int(cell[1], 36)
        ntype = int(cell[0], 36)
        notes.append(_SusNote(tick, lane, width, ntype, til, speed))
    return notes


def _get_note_stream(stream: list[_SusNote]) -> list[list[_SusNote]]:
    sorted_stream = sorted(stream, key=lambda n: n.tick)
    slides: list[list[_SusNote]] = []
    current: list[_SusNote] = []
    new_slide = True
    for note in sorted_stream:
        if new_slide:
            current = []
            new_slide = False
        current.append(note)
        if note.type == 2:
            slides.append(current)
            new_slide = True
    return slides


def _parse_hispeed_entry(entry: str) -> tuple[int, int, float] | None:
    apos = entry.find("'")
    if apos == -1:
        return None
    colon = entry.find(":", apos + 1)
    if colon == -1:
        return None
    try:
        return (
            int(entry[:apos]),
            int(entry[apos + 1 : colon]),
            float(entry[colon + 1 :]),
        )
    except ValueError:
        return None


def _is_command(line: str) -> bool:
    if line[1:2].isdigit():
        return False
    first_quote = line.find('"')
    if first_quote != -1:
        last_quote = line.rfind('"')
        if first_quote != last_quote:
            space = line.find(" ")
            if space != -1 and ":" in line[:space]:
                return False
            return True
    return ":" not in line


# MAIN LOADER


def load(fp: TextIO) -> Score:
    return loads(fp.read())


def loads(data: str) -> Score:
    ticks_per_beat = TICKS_PER_BEAT
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
    volume_data: list[str] = []

    taps: list[_SusNote] = []
    directionals: list[_SusNote] = []
    slide_streams: dict[int, list[_SusNote]] = {}
    guide_streams: dict[int, list[_SusNote]] = {}

    # PHASE 1: first pass to get bar_lengths, ticks_per_beat, and MEASUREBS
    measure_offset = 0
    lines_to_process: list[tuple[str, int]] = []  # (line, measure_offset)
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

    # PHASE 2: second pass for everything else (needs bars for tick calculation)
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
            if header.startswith("VOLUME"):
                volume_data.append(line_data)
            continue

        if len(header) == 5 and header.endswith("02") and header[:3].isdigit():
            pass  # already handled in phase 1
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
        elif len(header) == 6 and header[3] == "9":
            measure = int(header[:3]) + m_offset
            channel = int(header[5], 36)
            guide_streams.setdefault(channel, []).extend(
                _get_notes(header, line_data, bars, measure, current_til)
            )

    # Build slide/guide note streams
    slides: list[list[_SusNote]] = []
    for stream in slide_streams.values():
        slides.extend(_get_note_stream(stream))

    guides: list[list[_SusNote]] = []
    for stream in guide_streams.values():
        guides.extend(_get_note_stream(stream))

    # Deduplicate slides/guides sharing same start+end (tick, lane).
    # Game's noteInfoDict merges notes at same (time, lane), so duplicate
    # slides from different channels collapse into one.
    def _dedup_holds(holds: list[list[_SusNote]]) -> list[list[_SusNote]]:
        seen: set[tuple[int, int, int, int]] = set()
        result: list[list[_SusNote]] = []
        for hold in holds:
            if len(hold) < 2:
                continue
            key = (hold[0].tick, hold[0].lane, hold[-1].tick, hold[-1].lane)
            if key in seen:
                continue
            seen.add(key)
            result.append(hold)
        return result

    slides = _dedup_holds(slides)
    guides = _dedup_holds(guides)

    # Parse volumes
    volumes: list[tuple[int, float]] = []
    for vol_str in volume_data:
        stripped = vol_str.strip('"').replace(" ", "")
        for entry_str in stripped.split(","):
            parsed = _parse_hispeed_entry(entry_str)
            if parsed:
                measure, tick_offset, value = parsed
                measure_ticks = _get_ticks(bars, measure, 0, 1)
                volumes.append((measure_ticks + tick_offset, value))

    # PHASE 3: SUS → Score (matching ChartMaker susToScore)
    return _sus_to_score(
        taps,
        directionals,
        slides,
        guides,
        sorted(bpm_data_lines, key=lambda x: x[0]),
        bar_lengths,
        tils,
        volumes,
        title,
        artist,
        designer,
        wave_offset,
        requests,
    )


def _sus_to_score(
    sus_taps: list[_SusNote],
    sus_directionals: list[_SusNote],
    sus_slides: list[list[_SusNote]],
    sus_guides: list[list[_SusNote]],
    sus_bpms: list[tuple[int, float]],
    bar_lengths: list[tuple[int, float]],
    tils: list[list[tuple[int, float]]],
    sus_volumes: list[tuple[int, float]],
    title: str,
    artist: str,
    designer: str,
    wave_offset: float,
    requests: list[str],
) -> Score:
    # BUILD LOOKUP SETS (matching ChartMaker exactly)
    flicks: dict[str, Literal["up", "left", "right"]] = {}
    criticals: set[str] = set()
    step_ignore: set[str] = set()
    ease_ins: set[str] = set()
    ease_outs: set[str] = set()
    slide_keys: set[str] = set()
    frictions: set[str] = set()
    hidden_holds: set[str] = set()

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

    for t in sus_taps:
        key = _note_key(t.tick, t.lane)
        if t.type == 2:
            criticals.add(key)
        elif t.type == 3:
            step_ignore.add(key)
        elif t.type == 5:
            frictions.add(key)
        elif t.type == 6:
            criticals.add(key)
            frictions.add(key)
        elif t.type == 7:
            hidden_holds.add(key)
        elif t.type == 8:
            hidden_holds.add(key)
            criticals.add(key)

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

    # Volume
    for tick, vol in sus_volumes:
        notes.append(Volume(beat=_tick_to_beat(tick), volume=vol))

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

    # TAPS → Singles/Skills/Fever
    # Game's AddNormalNoteInfo merges taps at same (tick, lane) via Update,
    # so we deduplicate by (tick, lane) to avoid double-counting.
    fever_chance: float | None = None
    fever_start: float | None = None
    seen_tap_keys: set[str] = set()

    for note in sorted(sus_taps, key=lambda x: x.tick):
        if note.type == 4:
            notes.append(Skill(beat=_tick_to_beat(note.tick)))
            continue

        if note.lane == FEVER_LANE and note.width == 1:
            if note.type == 1:
                fever_chance = _tick_to_beat(note.tick)
                notes.append(FeverChance(beat=fever_chance))
            elif note.type == 2:
                fever_start = _tick_to_beat(note.tick)
                notes.append(FeverStart(beat=fever_start))
            continue

        # 3=step_ignore marker (Skip category, dropped by game), 7/8=hidden hold markers
        if note.type in (3, 7, 8):
            continue

        if note.lane < MIN_LANE or note.lane > MAX_LANE:
            continue

        key = _note_key(note.tick, note.lane)
        if key in slide_keys:
            continue

        if key in seen_tap_keys:
            continue
        seen_tap_keys.add(key)

        is_critical = key in criticals
        is_friction = key in frictions
        direction = flicks.get(key)

        notes.append(
            Single(
                beat=_tick_to_beat(note.tick),
                critical=is_critical,
                lane=_sus_to_usc_lane(note.lane, note.width),
                size=_sus_to_usc_size(note.width),
                timeScaleGroup=note.til,
                speedRatio=note.speedRatio,
                trace=is_friction,
                direction=direction,
            )
        )

    # SLIDES & GUIDES (matching ChartMaker slideFillFunc)
    def _process_holds(hold_list: list[list[_SusNote]], is_guide: bool) -> None:
        for hold in hold_list:
            start_notes = [n for n in hold if n.type in (1, 2)]
            if not start_notes or len(hold) < 2:
                continue

            start_key = _note_key(hold[0].tick, hold[0].lane)
            critical = start_key in criticals

            if is_guide:
                guide_note = Guide(color="yellow" if critical else "green", fade="out")
                for note in hold:
                    key = _note_key(note.tick, note.lane)
                    ease: Literal["in", "out", "linear"] = "linear"
                    if key in ease_ins:
                        ease = "in"
                    elif key in ease_outs:
                        ease = "out"

                    guide_note.append(
                        GuidePoint(
                            beat=_tick_to_beat(note.tick),
                            ease=ease,
                            lane=_sus_to_usc_lane(note.lane, note.width),
                            size=_sus_to_usc_size(note.width),
                            timeScaleGroup=note.til,
                            speedRatio=note.speedRatio,
                        )
                    )
                notes.append(guide_note)
            else:
                slide_note = Slide(critical=critical)
                for note in hold:
                    key = _note_key(note.tick, note.lane)
                    ease: Literal["in", "out", "linear"] = "linear"
                    if key in ease_ins:
                        ease = "in"
                    elif key in ease_outs:
                        ease = "out"
                    beat = _tick_to_beat(note.tick)
                    lane = _sus_to_usc_lane(note.lane, note.width)
                    size = _sus_to_usc_size(note.width)

                    if note.type == 1:  # start
                        is_hidden = key in hidden_holds
                        is_friction = key in frictions
                        if is_hidden:
                            judge_type = "none"
                        elif is_friction:
                            judge_type = "trace"
                        else:
                            judge_type = "normal"

                        slide_note.append(
                            SlideStartPoint(
                                beat=beat,
                                critical=critical,
                                ease=ease,
                                judgeType=judge_type,
                                lane=lane,
                                size=size,
                                timeScaleGroup=note.til,
                                speedRatio=note.speedRatio,
                            )
                        )

                    elif note.type == 2:  # end
                        is_hidden = key in hidden_holds
                        is_friction = key in frictions
                        if is_hidden:
                            judge_type = "none"
                        elif is_friction:
                            judge_type = "trace"
                        else:
                            judge_type = "normal"

                        end_critical = critical or (key in criticals)
                        direction = flicks.get(key)

                        slide_note.append(
                            SlideEndPoint(
                                beat=beat,
                                critical=end_critical,
                                judgeType=judge_type,
                                lane=lane,
                                size=size,
                                timeScaleGroup=note.til,
                                speedRatio=note.speedRatio,
                                direction=direction,
                            )
                        )

                    elif note.type in (3, 5):  # mid
                        # Normal (type 3, no step_ignore): changes shape + adds combo (tick + critical)
                        # Hidden (type 5): changes shape, no combo (tick + critical=None)
                        # Skip (type 3 + step_ignore): no shape change, adds combo (attach + critical)
                        step_type: Literal["tick", "attach"] = "tick"
                        mid_critical: bool | None = critical

                        if note.type == 5:
                            mid_critical = None
                        elif key in step_ignore:
                            step_type = "attach"

                        slide_note.append(
                            SlideRelayPoint(
                                beat=beat,
                                ease=ease,
                                lane=lane,
                                size=size,
                                timeScaleGroup=note.til,
                                type=step_type,
                                critical=mid_critical,
                                speedRatio=note.speedRatio,
                            )
                        )

                notes.append(slide_note)

    _process_holds(sus_slides, False)
    _process_holds(sus_guides, True)

    notes.sort(key=lambda x: x.get_sus_sort_number())

    metadata = MetaData(
        title=title,
        artist=artist,
        designer=designer,
        waveoffset=-wave_offset,
        requests=requests if requests else None,
    )

    return Score(metadata, notes)
