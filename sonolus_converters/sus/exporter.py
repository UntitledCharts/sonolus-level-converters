import math

from copy import deepcopy
from pathlib import Path
import io
from typing import Union

from typing import cast
from ..version import __version__
from ..notes.score import Score
from ..notes.bpm import Bpm
from ..notes.timescale import TimeScaleGroup, TimeScalePoint
from ..notes.single import Single, Skill, FeverStart, FeverChance
from ..notes.slide import Slide, SlideStartPoint, SlideRelayPoint, SlideEndPoint
from ..notes.guide import Guide, GuidePoint
from ..notes.volume import Volume

TICKS_PER_BEAT = 480
MIN_LANE = 2
MAX_LANE = 13


def _beat_to_tick(beat: float) -> int:
    return round(TICKS_PER_BEAT * beat)


def _usc_to_sus_lane(lane: float, size: float) -> int:
    return int(lane - size + 8)


def _usc_to_sus_width(size: float) -> int:
    return int(math.ceil(size * 2))


def _note_key(tick: int, lane: int) -> str:
    return f"{tick}-{lane}"


def _to_base36(n: int) -> str:
    if n < 0:
        return "0"
    chars = "0123456789abcdefghijklmnopqrstuvwxyz"
    if n == 0:
        return "0"
    result = ""
    while n > 0:
        result = chars[n % 36] + result
        n //= 36
    return result


def _format_number(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return str(value)


# SUS INTERMEDIATE DATA


class _SusNote:
    __slots__ = ("tick", "lane", "width", "type", "speedRatio")

    def __init__(
        self, tick: int, lane: int, width: int, ntype: int, speedRatio: float = 1.0
    ):
        self.tick = tick
        self.lane = lane
        self.width = width
        self.type = ntype
        self.speedRatio = speedRatio


class _ChannelProvider:
    def __init__(self):
        self.channels: dict[int, tuple[int, int]] = {k: (0, 0) for k in range(36)}

    def generate(self, start_tick: int, end_tick: int) -> int:
        for key, (s, e) in self.channels.items():
            if (s == 0 and e == 0) or end_tick < s or start_tick > e:
                self.channels[key] = (start_tick, end_tick)
                return key
        raise RuntimeError("No more slide channels available")


# SUS WRITING


class _NoteMap:
    def __init__(self):
        self.data: list[tuple[int, str, float]] = []  # (tick_offset, data, speedRatio)
        self.ticks_per_measure: int = 0


def _score_to_sus(
    score: Score,
) -> tuple[
    list[_SusNote],
    list[_SusNote],
    list[list[_SusNote]],
    list[list[_SusNote]],
    list[tuple[int, float]],
    list[tuple[int, float]],
    list[list[tuple[int, float]]],
    list[tuple[int, float]],
]:
    taps: list[_SusNote] = []
    directionals: list[_SusNote] = []
    slides: list[list[_SusNote]] = []
    guides: list[list[_SusNote]] = []
    bpms: list[tuple[int, float]] = []
    bar_lengths: list[tuple[int, float]] = [(0, 4.0)]
    tils: list[list[tuple[int, float]]] = []
    volumes: list[tuple[int, float]] = []

    critical_keys: set[str] = set()

    til_index = 0
    for note in score.notes:
        if isinstance(note, Bpm):
            bpms.append((_beat_to_tick(note.beat), note.bpm))

        elif isinstance(note, Volume):
            volumes.append((_beat_to_tick(note.beat), note.volume))

        elif isinstance(note, TimeScaleGroup):
            til: list[tuple[int, float]] = []
            for cp in cast(TimeScaleGroup, note).changes:
                cp = cast(TimeScalePoint, cp)
                til.append((_beat_to_tick(cp.beat), cp.timeScale))
            tils.append(til)
            til_index += 1

        elif isinstance(note, Skill):
            taps.append(_SusNote(_beat_to_tick(note.beat), 0, 1, 4))

        elif isinstance(note, FeverChance):
            taps.append(_SusNote(_beat_to_tick(note.beat), 15, 1, 1))

        elif isinstance(note, FeverStart):
            taps.append(_SusNote(_beat_to_tick(note.beat), 15, 1, 2))

        elif isinstance(note, Single):
            tick = _beat_to_tick(note.beat)
            lane = _usc_to_sus_lane(note.lane, note.size)
            width = _usc_to_sus_width(note.size)
            sr = note.speedRatio

            tap_type = 5 if note.trace else 1
            if note.critical:
                tap_type += 1
                critical_keys.add(_note_key(tick, lane))

            taps.append(_SusNote(tick, lane, width, tap_type, sr))

            if note.direction:
                dir_type = {"up": 1, "left": 3, "right": 4}[note.direction]
                directionals.append(_SusNote(tick, lane, width, dir_type, sr))

        elif isinstance(note, Slide):
            slide: list[_SusNote] = []
            conns = sorted(note.connections, key=lambda c: c.beat)
            start_tick = _beat_to_tick(conns[0].beat)

            for step in conns:
                tick = _beat_to_tick(step.beat)
                lane = _usc_to_sus_lane(step.lane, step.size)
                width = _usc_to_sus_width(step.size)
                sr = step.speedRatio

                if isinstance(step, SlideStartPoint):
                    slide.append(_SusNote(tick, lane, width, 1, sr))

                    has_ease = step.ease != "linear"
                    is_hidden = step.judgeType == "none"
                    is_trace = step.judgeType == "trace"

                    if has_ease:
                        dir_type = 2 if step.ease == "in" else 6
                        directionals.append(_SusNote(tick, lane, width, dir_type, sr))

                    tap_type = 7 if is_hidden else (5 if is_trace else 1)
                    already_critical = _note_key(tick, lane) in critical_keys
                    if step.critical and not already_critical:
                        tap_type += 1
                        critical_keys.add(_note_key(tick, lane))

                    if tap_type > 1:
                        taps.append(_SusNote(tick, lane, width, tap_type, sr))

                elif isinstance(step, SlideRelayPoint):
                    # Normal (type 3): changes shape + adds combo (tick + critical)
                    # Hidden (type 5): changes shape, no combo (tick + critical=None)
                    # Skip (type 3 + tap): no shape change, adds combo (attach + critical)
                    slide_type = 5 if step.critical is None else 3
                    slide.append(_SusNote(tick, lane, width, slide_type, sr))

                    if step.critical is None and step.type == "tick":
                        pass  # hidden step, no tap
                    elif step.type == "attach":
                        taps.append(_SusNote(tick, lane, width, 3, sr))
                    elif step.ease != "linear":
                        taps.append(_SusNote(tick, lane, width, 1, sr))
                        dir_type = 2 if step.ease == "in" else 6
                        directionals.append(_SusNote(tick, lane, width, dir_type, sr))

                elif isinstance(step, SlideEndPoint):
                    slide.append(_SusNote(tick, lane, width, 2, sr))

                    is_hidden = step.judgeType == "none"
                    is_trace = step.judgeType == "trace"

                    if step.direction:
                        dir_type = {"up": 1, "left": 3, "right": 4}[step.direction]
                        directionals.append(_SusNote(tick, lane, width, dir_type, sr))

                        if step.critical and not note.critical and not is_trace:
                            taps.append(_SusNote(tick, lane, width, 2, sr))

                    end_type = 7 if is_hidden else (5 if is_trace else 1)
                    if step.critical:
                        end_type += 1
                        critical_keys.add(_note_key(tick, lane))

                    if end_type not in (1, 2):
                        taps.append(_SusNote(tick, lane, width, end_type, sr))

            slides.append(slide)

        elif isinstance(note, Guide):
            guide_slide: list[_SusNote] = []
            points = sorted(note.midpoints, key=lambda p: p.beat)
            is_critical = note.color == "yellow"
            start_tick = _beat_to_tick(points[0].beat) if points else 0

            for idx, step in enumerate(points):
                step = cast(GuidePoint, step)
                tick = _beat_to_tick(step.beat)
                lane = _usc_to_sus_lane(step.lane, step.size)
                width = _usc_to_sus_width(step.size)
                sr = step.speedRatio

                if idx == 0:
                    guide_slide.append(_SusNote(tick, lane, width, 1, sr))

                    has_ease = step.ease != "linear"
                    if has_ease:
                        dir_type = 2 if step.ease == "in" else 6
                        directionals.append(_SusNote(tick, lane, width, dir_type, sr))

                    already_critical = _note_key(tick, lane) in critical_keys
                    tap_type = 7
                    if is_critical and not already_critical:
                        tap_type = 8
                        critical_keys.add(_note_key(tick, lane))

                    guide_already_on_critical = already_critical
                    if not ((tap_type in (7, 8)) and guide_already_on_critical):
                        taps.append(_SusNote(tick, lane, width, tap_type, sr))

                elif idx == len(points) - 1:
                    guide_slide.append(_SusNote(tick, lane, width, 2, sr))
                    # guide ends: no flick, no friction
                    # but need critical marker if guide is critical
                    if is_critical:
                        already_critical = _note_key(tick, lane) in critical_keys
                        if not already_critical:
                            taps.append(_SusNote(tick, lane, width, 8, sr))
                            critical_keys.add(_note_key(tick, lane))

                else:
                    guide_slide.append(_SusNote(tick, lane, width, 5, sr))

                    if step.ease != "linear":
                        tap_type = 8 if is_critical else 7
                        already_critical = _note_key(tick, lane) in critical_keys
                        if not ((tap_type in (7, 8)) and already_critical):
                            taps.append(_SusNote(tick, lane, width, tap_type, sr))
                        dir_type = 2 if step.ease == "in" else 6
                        directionals.append(_SusNote(tick, lane, width, dir_type, sr))

            guides.append(guide_slide)

    if not bpms:
        bpms.append((0, 120.0))

    return taps, directionals, slides, guides, bpms, bar_lengths, tils, volumes


# SUS TEXT GENERATION


def _dump_sus(
    taps: list[_SusNote],
    directionals: list[_SusNote],
    slides: list[list[_SusNote]],
    guides: list[list[_SusNote]],
    bpms: list[tuple[int, float]],
    bar_lengths: list[tuple[int, float]],
    tils: list[list[tuple[int, float]]],
    volumes: list[tuple[int, float]],
    metadata: Score,
    comment: str,
    measure_extensions: bool = False,
) -> str:
    lines: list[str] = []
    tpb = TICKS_PER_BEAT

    lines.append(comment)
    if metadata.metadata.title:
        lines.append(f'#TITLE "{metadata.metadata.title}"')
    if metadata.metadata.artist:
        lines.append(f'#ARTIST "{metadata.metadata.artist}"')
    if metadata.metadata.designer:
        lines.append(f'#DESIGNER "{metadata.metadata.designer}"')
    lines.append(f"#WAVEOFFSET {_format_number(-metadata.metadata.waveoffset)}")
    lines.append("")
    if metadata.metadata.requests:
        for req in metadata.metadata.requests:
            lines.append(f'#REQUEST "{req}"')
    else:
        lines.append(f'#REQUEST "ticks_per_beat {tpb}"')
    lines.append("")

    # MEASUREBS: for measures >= 1000, emit #MEASUREBS <base> and use offset
    mbs_base = [0]  # mutable for closure

    def _mbs(measure: int, out: list[str]) -> str:
        if measure_extensions:
            base = (measure // 1000) * 1000
            if base != mbs_base[0]:
                out.append(f"#MEASUREBS {base}")
                mbs_base[0] = base
            return f"{measure - base:03d}"
        return f"{measure:03d}"

    sorted_bl = sorted(bar_lengths, key=lambda x: x[0])
    sorted_bpms = sorted(bpms, key=lambda x: x[0])

    for measure, length in sorted_bl:
        mstr = _mbs(measure, lines)
        lines.append(f"#{mstr}02: {_format_number(length)}")
    lines.append("")

    # Build bar tick lookup (reversed for searching)
    acc = 0
    bar_tick_list: list[tuple[int, float, int]] = []  # (measure, length, start_tick)
    for i, (measure, length) in enumerate(sorted_bl):
        start_tick = acc
        if i + 1 < len(sorted_bl):
            acc += int((sorted_bl[i + 1][0] - measure) * length * tpb)
        bar_tick_list.append((measure, length, start_tick))
    bar_tick_list.reverse()

    def get_measure_from_tick(tick: int) -> int:
        for measure, length, start_tick in bar_tick_list:
            if tick >= start_tick:
                return measure + int((tick - start_tick) / tpb / length)
        return 0

    def get_tick_from_measure(m: int) -> int:
        for measure, length, start_tick in bar_tick_list:
            if measure <= m:
                return start_tick + int((m - measure) * length * tpb)
        return 0

    # BPM definitions
    bpm_ids: dict[float, str] = {}
    for tick, bpm_val in sorted_bpms:
        if bpm_val not in bpm_ids:
            ident = _to_base36(len(bpm_ids) + 1).upper().zfill(2)
            bpm_ids[bpm_val] = ident
            lines.append(f"#BPM{ident}: {_format_number(bpm_val)}")

    # BPM placements grouped by measure
    bpm_by_measure: dict[int, list[tuple[int, float]]] = {}
    for tick, bpm_val in sorted_bpms:
        m = get_measure_from_tick(tick)
        bpm_by_measure.setdefault(m, []).append((tick, bpm_val))

    for m in sorted(bpm_by_measure.keys()):
        m_tick = get_tick_from_measure(m)
        next_tick = get_tick_from_measure(m + 1)
        tpm = next_tick - m_tick
        bpm_entries = bpm_by_measure[m]

        gcd = tpm
        for btick, _ in bpm_entries:
            gcd = math.gcd(btick - m_tick, gcd)

        count = tpm // gcd
        bpm_data = ["00"] * count
        for btick, bval in bpm_entries:
            idx = (btick - m_tick) // gcd
            bpm_data[idx] = bpm_ids[bval]

        lines.append(f"#{_mbs(m, lines)}08: {''.join(bpm_data)}")
    lines.append("")

    # TIL layers
    for i, til in enumerate(tils):
        entries: list[str] = []
        for tick, speed in sorted(til, key=lambda x: x[0]):
            m = get_measure_from_tick(tick)
            offset = tick - get_tick_from_measure(m)
            entries.append(f"{m}'{offset}:{_format_number(speed)}")
        til_id = _to_base36(i).upper().zfill(2)
        lines.append(f'#TIL{til_id}: "{", ".join(entries)}"')

    # Volume
    if volumes:
        vol_entries: list[str] = []
        for tick, vol in sorted(volumes, key=lambda x: x[0]):
            m = get_measure_from_tick(tick)
            offset = tick - get_tick_from_measure(m)
            vol_entries.append(f"{m}'{offset}:{_format_number(vol)}")
        lines.append(f'#VOLUME: "{", ".join(vol_entries)}"')

    lines.append("#HISPEED 00")
    lines.append("#MEASUREHS 00")
    lines.append("")

    # NOTE DATA
    measures_map: dict[int, dict[str, _NoteMap]] = {}

    def append_data(tick: int, info: str, data_str: str, speed: float = 1.0):
        for measure, length, start_tick in bar_tick_list:
            if tick >= start_tick:
                cur_measure = measure + int((tick - start_tick) / tpb / length)
                if cur_measure not in measures_map:
                    measures_map[cur_measure] = {}
                nm = measures_map[cur_measure].setdefault(info, _NoteMap())
                nm.data.append((tick - start_tick, data_str, speed))
                nm.ticks_per_measure = int(length * tpb)
                break

    def append_note(n: _SusNote, prefix: str, channel: str = ""):
        info = prefix + _to_base36(n.lane) + channel
        append_data(n.tick, info, str(n.type) + _to_base36(n.width), n.speedRatio)

    def write_note_lines() -> list[str]:
        result: list[str] = []
        for measure in sorted(measures_map.keys()):
            mstr = _mbs(measure, result)
            note_map = measures_map[measure]
            for info, nm in note_map.items():
                conflicts: list[tuple[int, str, float]] = []

                gcd = nm.ticks_per_measure
                for tick_off, _, _ in nm.data:
                    gcd = math.gcd(tick_off, gcd)

                count = nm.ticks_per_measure // gcd
                has_speed = any(abs(sr - 1.0) > 0.0001 for _, _, sr in nm.data)

                data = ["00,1.0" if has_speed else "00"] * count
                for tick_off, d, sr in nm.data:
                    idx = (tick_off % nm.ticks_per_measure) // gcd
                    if data[idx][:2] != "00":
                        conflicts.append((tick_off, d, sr))
                    else:
                        data[idx] = f"{d},{_format_number(sr)}" if has_speed else d

                sep = " " if has_speed else ""
                result.append(f"#{mstr}{info}:{sep.join(data)}")

                while conflicts:
                    temp: list[tuple[int, str, float]] = []
                    data2 = ["00,1.0" if has_speed else "00"] * count
                    for tick_off, d, sr in conflicts:
                        idx = (tick_off % nm.ticks_per_measure) // gcd
                        if data2[idx][:2] != "00":
                            temp.append((tick_off, d, sr))
                        else:
                            data2[idx] = f"{d},{_format_number(sr)}" if has_speed else d
                    result.append(f"#{mstr}{info}:{sep.join(data2)}")
                    conflicts = temp

        return result

    # Taps
    measures_map.clear()
    for tap in sorted(taps, key=lambda n: n.tick):
        append_note(tap, "1")
    lines.extend(write_note_lines())

    # Directionals
    measures_map.clear()
    for d in sorted(directionals, key=lambda n: n.tick):
        append_note(d, "5")
    lines.extend(write_note_lines())

    # Slides
    measures_map.clear()
    ch_prov = _ChannelProvider()
    for slide in sorted(slides, key=lambda s: s[0].tick):
        ch = ch_prov.generate(slide[0].tick, slide[-1].tick)
        ch_str = _to_base36(ch)
        for n in slide:
            append_note(n, "3", ch_str)
    lines.extend(write_note_lines())

    # Guides
    measures_map.clear()
    ch_prov_g = _ChannelProvider()
    for guide in sorted(guides, key=lambda s: s[0].tick):
        ch = ch_prov_g.generate(guide[0].tick, guide[-1].tick)
        ch_str = _to_base36(ch)
        for n in guide:
            append_note(n, "9", ch_str)
    lines.extend(write_note_lines())

    lines.append("")
    return "\n".join(lines)


# PUBLIC API


def export(
    path: Union[str, Path, io.BytesIO, io.StringIO, io.TextIOBase],
    score: Score,
    allow_layers: bool = False,
    allow_extended_lanes: bool = False,
    delete_damage: bool = True,
    keep_note_speed_ratios: bool = False,
    measure_extensions: bool = False,
):
    score = deepcopy(score)
    score.shift()
    score.replace_extended_ease()
    score.replace_extended_guide_colors()
    score.delete_fake_notes()
    if delete_damage:
        score.delete_damage_notes()
    if not allow_extended_lanes:
        score.strip_extended_lanes()
    if not keep_note_speed_ratios:
        score.strip_speed_ratios()

    if not allow_layers:
        tsg_count = sum(1 for n in score.notes if isinstance(n, TimeScaleGroup))
        if tsg_count > 1:
            raise ValueError("Layers found where allow_layers is false")

    taps, directionals, slides, guides, bpms, bl, tils, volumes = _score_to_sus(score)

    sus_text = _dump_sus(
        taps,
        directionals,
        slides,
        guides,
        bpms,
        bl,
        tils,
        volumes,
        score,
        f"This file was generated by sonolus-level-converters {__version__}",
        measure_extensions=measure_extensions,
    )

    if isinstance(path, (str, Path)):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            f.write(sus_text)
    elif isinstance(path, (io.StringIO, io.TextIOBase)):
        path.write(sus_text)
        path.seek(0)
    elif isinstance(path, io.BytesIO):
        path.write(sus_text.encode("utf-8"))
        path.seek(0)
    else:
        raise TypeError(f"Unsupported path type: {type(path)}")
