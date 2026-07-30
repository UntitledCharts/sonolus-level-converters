"""holodori sus -> Score. a sekai-sus dialect decoded off the game's SusConverter."""

from typing import TextIO, Literal
import re

from ..notes.score import Score
from ..notes.metadata import MetaData
from ..notes.bpm import Bpm
from ..notes.timescale import TimeScaleGroup, TimeScalePoint
from ..notes.single import Single
from ..notes.holodorievents import (
    HolodoriSkill,
    HolodoriChargeStart,
    HolodoriChargeEnd,
    HolodoriFeverStart,
    HolodoriFeverEnd,
)
from ..notes.slide import Slide, SlideStartPoint, SlideRelayPoint, SlideEndPoint
from ..notes.guide import Guide, GuidePoint

from ..sus.loader import (
    TICKS_PER_BEAT,
    MIN_LANE,
    MAX_LANE,
    _Bar,
    _SusNote,
    _get_bars,
    _get_ticks,
    _get_note_stream,
    _tick_to_beat,
    _sus_to_usc_lane,
    _sus_to_usc_size,
    _note_key,
)


def _char_to_int(c: str) -> int:
    """SusUtility.CharToInt: case-sensitive base62 (0-9, a-z = 10-35, A-Z = 36-61)"""
    o = ord(c)
    if 48 <= o <= 57:
        return o - 48
    if 97 <= o <= 122:
        return o - 87
    if 65 <= o <= 90:
        return o - 29
    return 0


def _holodori_notes(
    header: str, lane_char: str, data: str, bars: list[_Bar], measure: int, til: int
) -> list[_SusNote]:
    """parse a note line. the data is a grid of positions: a "0x" token skips (base62 d1*62 + d2)
    empty positions (compressed empties); any other 2-char cell is one position (kind = char0,
    width = char1; kind 0 = empty). beat = position / total positions."""
    notes: list[_SusNote] = []
    lane = _char_to_int(lane_char)
    parsed: list[tuple[int, int, int]] = []  # (position, kind, width)
    i = 0
    pos = 0
    n = len(data)
    while i < n:
        if i + 4 <= n and data[i] == "0" and data[i + 1] == "x":
            pos += _char_to_int(data[i + 2]) * 62 + _char_to_int(data[i + 3])
            i += 4
        elif i + 2 <= n:
            if data[i] != "0":
                parsed.append((pos, _char_to_int(data[i]), _char_to_int(data[i + 1])))
            pos += 1
            i += 2
        else:
            break
    total = pos
    if total <= 0:
        return notes
    for p, kind, width in parsed:
        notes.append(
            _SusNote(_get_ticks(bars, measure, p, total), lane, width, kind, til, 1.0)
        )
    return notes


def _meta_cells(data: str) -> list[tuple[int, str, int]]:
    """bpm (08) / nms (0A) grid -> (position, id, total). same 0x-compressed grid, but a leading-0
    cell like "05" is id 5 (only "00" is empty), so it can't reuse _holodori_notes."""
    data = data.strip()
    cells: list[tuple[int, str]] = []
    i = 0
    pos = 0
    n = len(data)
    while i < n:
        if i + 4 <= n and data[i] == "0" and data[i + 1] == "x":
            pos += _char_to_int(data[i + 2]) * 62 + _char_to_int(data[i + 3])
            i += 4
        elif i + 2 <= n:
            cell = data[i : i + 2]
            if cell != "00":
                cells.append((pos, cell))
            pos += 1
            i += 2
        else:
            break
    return [(p, c, pos) for p, c in cells] if pos > 0 else []


def _meta_values(data: str) -> list[tuple[int, int, int]]:
    """0B/0C/0D grid -> (position, value, total). the cell is a base62 pair, so "10" is 62."""
    return [
        (pos, _char_to_int(cell[0]) * 62 + _char_to_int(cell[1]), total)
        for pos, cell, total in _meta_cells(data)
    ]


_FEVER_POINT_TYPES: dict[tuple[str, int], str] = {
    ("C", 1): "chargeStart",
    ("C", 2): "chargeEnd",
    ("D", 1): "feverStart",
    ("D", 2): "feverEnd",
}

_SP_SKILL_RE = re.compile(r"^(\d{3}) (\d+)/(\d+) (\d+)")


def load(fp: TextIO) -> Score:
    return loads(fp.read())


def loads(data: str) -> Score:
    ticks_per_beat = TICKS_PER_BEAT  # positions are fractional i/N; the file's ticks_per_beat is ignored
    music_id = ""
    wave_offset = 0.0
    base_bpm = 120.0

    bar_lengths: list[tuple[int, float]] = []
    bpm_definitions: dict[str, float] = {}
    bpm_data_lines: list[tuple[int, float]] = []
    nms_definitions: dict[str, float] = {}
    nms_data_lines: list[tuple[int, float]] = []
    color_definitions: dict[str, str] = {}

    sp_skill_points: list[tuple[int, int]] = []  # (tick, deck slot)
    fever_ticks: dict[str, list[int]] = {
        name: [] for name in _FEVER_POINT_TYPES.values()
    }

    taps: list[_SusNote] = []
    directionals: list[_SusNote] = []
    slide_streams: dict[int, list[_SusNote]] = {}
    ghost_streams: dict[int, list[_SusNote]] = {}
    ghost_colors: dict[int, str] = {}

    # PHASE 1: bar lengths
    for raw in data.splitlines():
        line = raw.strip()
        if not line.startswith("#"):
            continue
        colon = line.find(":", 1)
        if colon != -1:
            header = line[1:colon].strip()
            if len(header) == 5 and header[3:] == "02" and header[:3].isdigit():
                bar_lengths.append((int(header[:3]), float(line[colon + 1 :].strip())))
    if not bar_lengths:
        bar_lengths.append((0, 4.0))
    bars = _get_bars(bar_lengths, ticks_per_beat)

    # PHASE 2: everything else
    for raw in data.splitlines():
        line = raw.strip()
        if not line.startswith("#"):
            continue
        colon = line.find(":", 1)

        if colon == -1:  # space-separated meta directive
            parts = line[1:].split(None, 1)
            key = parts[0].upper() if parts else ""
            val = parts[1].strip().strip('"') if len(parts) > 1 else ""
            if key == "MUSIC_ID":
                music_id = val
            elif key == "WAVEOFFSET":
                wave_offset = float(val or 0)
            elif key == "BASEBPM":
                base_bpm = float(val or 120)
            elif key == "SP_SKILL":  # legacy sp skill line: #SP_SKILL mmm num/den slot
                sm = _SP_SKILL_RE.match(val)
                if sm:
                    den = int(sm.group(3))
                    tick = _get_ticks(
                        bars,
                        int(sm.group(1)),
                        int(sm.group(2)) if den else 0,
                        den or 1,
                    )
                    sp_skill_points.append((tick, int(sm.group(4))))
            continue

        header = line[1:colon].strip()
        line_data = line[colon + 1 :].strip()

        # ghost: #mmm 9 lane channel + 4-hex color id
        gm = re.match(
            r"^(\d{3})[0-9a-z]([0-9a-z])([0-9a-zA-Z])([0-9A-Fa-f]{4})$", header
        )
        if gm:
            measure = int(gm.group(1))
            channel = int(gm.group(3), 36)
            ghost_colors[channel] = gm.group(4)
            ghost_streams.setdefault(channel, []).extend(
                _holodori_notes(header, gm.group(2), line_data, bars, measure, 0)
            )
            continue

        if (
            header.startswith("COLOR") and len(header) == 9
        ):  # #COLORwwww: rgba (8 hex incl alpha)
            color_definitions[header[5:]] = line_data.strip()
            continue
        if header.startswith("BPM") and len(header) == 5:
            bpm_definitions[header[3:]] = float(line_data)
            continue
        if header.startswith("NMS") and len(header) == 5:
            nms_definitions[header[3:]] = float(line_data)
            continue
        if len(header) != 5 or not header[:3].isdigit():
            continue
        measure = int(header[:3])
        event, lane_char = header[3], header[4]

        if header[3:] == "02":
            continue  # bar length, handled in phase 1
        if header[3:] == "08":  # bpm change: each cell is a #BPMxx id
            for pos, cell, total in _meta_cells(line_data):
                bpm_data_lines.append(
                    (
                        _get_ticks(bars, measure, pos, total),
                        bpm_definitions.get(cell, base_bpm),
                    )
                )
            continue
        if header[3:] == "0A":  # NMS (hispeed) change: each cell is a #NMSxx id
            for pos, cell, total in _meta_cells(line_data):
                nms_data_lines.append(
                    (
                        _get_ticks(bars, measure, pos, total),
                        nms_definitions.get(cell, 1.0),
                    )
                )
            continue
        if header[3:] == "0B":  # sp skill: each cell is a deck slot number (1-5)
            for pos, value, total in _meta_values(line_data):
                if value >= 1:
                    sp_skill_points.append(
                        (_get_ticks(bars, measure, pos, total), value)
                    )
            continue
        if header[3:] in ("0C", "0D"):  # fever charge / fever section
            for pos, value, total in _meta_values(line_data):
                point_type = _FEVER_POINT_TYPES.get((lane_char, value))
                if point_type is not None:
                    fever_ticks[point_type].append(
                        _get_ticks(bars, measure, pos, total)
                    )
            continue

        if event == "1":  # tap channel
            taps.extend(_holodori_notes(header, lane_char, line_data, bars, measure, 0))
        elif event == "5":  # flick / directional channel
            directionals.extend(
                _holodori_notes(header, lane_char, line_data, bars, measure, 0)
            )

    # long notes: #mmm 3 lane channel  (channel groups one hold's segments)
    for raw in data.splitlines():
        line = raw.strip()
        m = re.match(r"^#(\d{3})3([0-9a-z])([0-9a-zA-Z]):(.+)$", line)
        if not m:
            continue
        measure, channel = int(m.group(1)), int(m.group(3), 36)
        slide_streams.setdefault(channel, []).extend(
            _holodori_notes(
                m.group(1) + "3" + m.group(2) + m.group(3),
                m.group(2),
                m.group(4).strip(),
                bars,
                measure,
                0,
            )
        )

    # group each channel into holds: FIFO-match each end (kind 2) to the OLDEST open start (kind 1),
    # taking the relays between them. LIFO would fuse interleaved slides into chart-long holds. de-dup
    # exact repeats first, since the dense multi-line encoding repeats points.
    slides: list[list[_SusNote]] = []
    for stream in slide_streams.values():
        seen: set[tuple[int, int, int, int]] = set()
        notes_sorted: list[_SusNote] = []
        for n in sorted(stream, key=lambda x: x.tick):
            key = (n.tick, n.lane, n.type, n.width)
            if key not in seen:
                seen.add(key)
                notes_sorted.append(n)
        start_stack: list[_SusNote] = []
        relay_stock: list[_SusNote] = []
        for n in notes_sorted:
            if n.type == 1:  # start
                start_stack.append(n)
            elif n.type == 2:  # end
                matched: _SusNote | None = None
                for j in range(len(start_stack)):
                    if start_stack[j].tick <= n.tick:
                        matched = start_stack.pop(j)
                        break
                if matched is None:
                    continue  # unmatched end is dropped
                relays = [r for r in relay_stock if matched.tick <= r.tick <= n.tick]
                for r in relays:
                    relay_stock.remove(r)
                slides.append([matched] + sorted(relays, key=lambda x: x.tick) + [n])
            else:  # relay
                relay_stock.append(n)
    ghosts: list[tuple[list[_SusNote], str | None]] = []
    for ch, stream in ghost_streams.items():
        color_id = ghost_colors.get(ch, "")
        rgba = color_definitions.get(color_id, color_id or None)
        for hold in _get_note_stream(stream):
            ghosts.append((hold, rgba))

    return _holodori_to_score(
        taps,
        directionals,
        slides,
        ghosts,
        sorted(bpm_data_lines),
        nms_data_lines,
        sp_skill_points,
        fever_ticks,
        music_id,
        wave_offset,
        ticks_per_beat,
    )


def _holodori_to_score(
    taps: list[_SusNote],
    directionals: list[_SusNote],
    slides: list[list[_SusNote]],
    ghosts: list[tuple[list[_SusNote], str | None]],
    bpms: list[tuple[int, float]],
    nms: list[tuple[int, float]],
    sp_skill_points: list[tuple[int, int]],
    fever_ticks: dict[str, list[int]],
    music_id: str,
    wave_offset: float,
    ticks_per_beat: int,
) -> Score:
    # overlay lookup sets keyed by (tick, lane)
    criticals: set[str] = set()
    step_ignore: set[str] = (
        set()
    )  # a relay marked here is attach/skip, not a shape point
    flicks: dict[str, Literal["up", "left", "right"]] = {}
    ease_ins: set[str] = set()
    ease_outs: set[str] = set()

    for d in directionals:
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

    for t in taps:
        key = _note_key(t.tick, t.lane)
        if t.type in (2, 6):
            criticals.add(key)
        elif t.type == 3:
            step_ignore.add(key)

    notes: list = []

    for tick, bpm in bpms or [(0, 120.0)]:
        notes.append(Bpm(beat=_tick_to_beat(tick), bpm=bpm))

    # NMS is a single hispeed layer -> one TimeScaleGroup
    tsg = TimeScaleGroup()
    if nms:
        for tick, mul in sorted(nms):
            tsg.append(TimeScalePoint(beat=_tick_to_beat(tick), timeScale=mul))
        if not any(p.beat == 0.0 for p in tsg.changes):
            tsg.insert(0, TimeScalePoint(beat=0.0, timeScale=1.0))
    else:
        tsg.append(TimeScalePoint(beat=0.0, timeScale=1.0))
    notes.append(tsg)

    for tick, slot in sorted(set(sp_skill_points)):
        notes.append(HolodoriSkill(beat=_tick_to_beat(tick), slot=slot))

    # the game drops the whole section unless it has exactly one of each point, in order
    points = [
        fever_ticks[name]
        for name in ("chargeStart", "chargeEnd", "feverStart", "feverEnd")
    ]
    if all(len(p) == 1 for p in points):
        charge_start, charge_end, fever_start, fever_end = (p[0] for p in points)
        if charge_start <= charge_end <= fever_start <= fever_end:
            notes.append(HolodoriChargeStart(beat=_tick_to_beat(charge_start)))
            notes.append(HolodoriChargeEnd(beat=_tick_to_beat(charge_end)))
            notes.append(HolodoriFeverStart(beat=_tick_to_beat(fever_start)))
            notes.append(HolodoriFeverEnd(beat=_tick_to_beat(fever_end)))

    # SINGLES. NORMAL (tap kind-1) and FLICK (directional kind-1/3/4) are disjoint; a tap with a
    # co-located directional is one flick. a directional on a hold start/end belongs to that slide.
    slide_end_keys = {
        _note_key(hold[-1].tick, hold[-1].lane) for hold in slides if len(hold) >= 2
    }
    slide_start_keys = {
        _note_key(hold[0].tick, hold[0].lane) for hold in slides if len(hold) >= 2
    }
    tap_keys = {_note_key(n.tick, n.lane) for n in taps if n.type == 1}

    for n in taps:
        if n.type != 1 or n.lane < MIN_LANE or n.lane > MAX_LANE:
            continue
        key = _note_key(n.tick, n.lane)
        if key in slide_start_keys:  # this tap is the hold head (emitted by the slide)
            continue
        direction = flicks.get(
            key
        )  # a co-located directional makes this one flick, not tap + flick
        notes.append(
            Single(
                beat=_tick_to_beat(n.tick),
                critical=key in criticals,
                lane=_sus_to_usc_lane(n.lane, n.width),
                size=_sus_to_usc_size(n.width),
                timeScaleGroup=0,
                speedRatio=n.speedRatio,
                trace=direction is not None,
                direction=direction,
            )
        )
    for n in directionals:  # standalone flicks (no tap / hold under them)
        direction = {1: "up", 3: "left", 4: "right"}.get(
            n.type
        )  # 2/5/6 are slide-ease markers
        if direction is None or n.lane < MIN_LANE or n.lane > MAX_LANE:
            continue
        key = _note_key(n.tick, n.lane)
        if key in slide_end_keys or key in slide_start_keys or key in tap_keys:
            continue
        notes.append(
            Single(
                beat=_tick_to_beat(n.tick),
                critical=key in criticals,
                lane=_sus_to_usc_lane(n.lane, n.width),
                size=_sus_to_usc_size(n.width),
                timeScaleGroup=0,
                speedRatio=n.speedRatio,
                trace=True,
                direction=direction,
            )
        )

    # tap kind-2 = critical taps. a co-located one only upgrades that note (via `criticals`); the
    # standalone rest are their own critical taps.
    emitted = {_note_key(n.tick, n.lane) for n in taps if n.type == 1}
    emitted |= {_note_key(n.tick, n.lane) for n in directionals if n.type in (1, 3, 4)}
    emitted |= {_note_key(p.tick, p.lane) for hold in slides for p in hold}
    for t in taps:
        if t.type != 2 or t.lane < MIN_LANE or t.lane > MAX_LANE:
            continue
        key = _note_key(t.tick, t.lane)
        if key in emitted:
            continue
        notes.append(
            Single(
                beat=_tick_to_beat(t.tick),
                critical=True,
                lane=_sus_to_usc_lane(t.lane, t.width),
                size=_sus_to_usc_size(t.width),
                timeScaleGroup=0,
                speedRatio=t.speedRatio,
                trace=False,
                direction=None,
            )
        )

    # HOLDS. first point = start (trace-tapped head), last = end (trace), rest = relays by kind:
    #   3 LongRelayActive: visible + combo -> attach (no shape change) if step_ignore, else tick (bends)
    #   4 LongBezierPoint / 5 LongRelayDeActive: hidden, shape, no combo (bezier pull is lost in usc)
    for hold in slides:
        if len(hold) < 2:
            continue
        start_key = _note_key(hold[0].tick, hold[0].lane)
        critical = start_key in criticals
        slide = Slide(critical=critical)
        last = len(hold) - 1
        for idx, n in enumerate(hold):
            key = _note_key(n.tick, n.lane)
            ease: Literal["in", "out", "linear"] = (
                "in" if key in ease_ins else ("out" if key in ease_outs else "linear")
            )
            beat = _tick_to_beat(n.tick)
            lane = _sus_to_usc_lane(n.lane, n.width)
            size = _sus_to_usc_size(n.width)

            if idx == 0:
                slide.append(
                    SlideStartPoint(
                        beat=beat,
                        critical=critical,
                        ease=ease,
                        judgeType="normal",
                        lane=lane,
                        size=size,
                        timeScaleGroup=0,
                        speedRatio=n.speedRatio,
                    )
                )
            elif idx == last:
                slide.append(
                    SlideEndPoint(
                        beat=beat,
                        critical=critical or key in criticals,
                        judgeType="trace",
                        lane=lane,
                        size=size,
                        timeScaleGroup=0,
                        speedRatio=n.speedRatio,
                        direction=flicks.get(key),
                    )
                )
            elif n.type == 3:
                slide.append(
                    SlideRelayPoint(
                        beat=beat,
                        ease=ease,
                        lane=lane,
                        size=size,
                        timeScaleGroup=0,
                        type="attach" if key in step_ignore else "tick",
                        critical=critical,
                        speedRatio=n.speedRatio,
                    )
                )
            else:
                slide.append(
                    SlideRelayPoint(
                        beat=beat,
                        ease=ease,
                        lane=lane,
                        size=size,
                        timeScaleGroup=0,
                        type="tick",
                        critical=None,
                        speedRatio=n.speedRatio,
                    )
                )
        slide.sort()
        notes.append(slide)

    # ghost notes -> guides. holodori guides hold at the #COLOR alpha (no fade); rgba in color_code.
    for hold, color_code in ghosts:
        if len(hold) < 2:
            continue
        guide = Guide(color="green", fade="none", color_code=color_code)
        for n in hold:
            key = _note_key(n.tick, n.lane)
            ease = (
                "in" if key in ease_ins else ("out" if key in ease_outs else "linear")
            )
            guide.append(
                GuidePoint(
                    beat=_tick_to_beat(n.tick),
                    ease=ease,
                    lane=_sus_to_usc_lane(n.lane, n.width),
                    size=_sus_to_usc_size(n.width),
                    timeScaleGroup=0,
                    speedRatio=n.speedRatio,
                )
            )
        notes.append(guide)

    notes.sort(key=lambda x: x.get_sus_sort_number())
    metadata = MetaData(
        title=music_id,
        artist="",
        designer="",
        waveoffset=-wave_offset,
        requests=[f"ticks_per_beat {ticks_per_beat}"],
    )
    return Score(metadata, notes)
