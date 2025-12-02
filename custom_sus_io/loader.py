import logging
import re

from collections import defaultdict
from typing import Callable, TextIO
from .schemas import Score, Note, Metadata

logger = logging.getLogger(__name__)


def process_metadata(lines: list[tuple[str]]) -> Metadata:
    result = {}
    for line in lines:
        if len(line) == 2:
            key, value = line
        else:
            key = line[0]
            value = None
        key = key[1:]
        value = value.strip('"') if value != None else None
        if key == "TITLE":
            result["title"] = value
        elif key == "SUBTITLE":
            result["subtitle"] = value
        elif key == "ARTIST":
            result["artist"] = value
        elif key == "GENRE":
            result["genre"] = value
        elif key == "DESIGNER":
            result["designer"] = value
        elif key == "DIFFICULTY":
            result["difficulty"] = value
        elif key == "PLAYLEVEL":
            result["playlevel"] = value
        elif key == "SONGID":
            result["songid"] = value
        elif key == "WAVE":
            result["wave"] = value
        elif key == "WAVEOFFSET":
            result["waveoffset"] = float(value)
        elif key == "JACKET":
            result["jacket"] = value
        elif key == "BACKGROUND":
            result["background"] = value
        elif key == "MOVIE":
            result["movie"] = value
        elif key == "MOVIEOFFSET":
            result["movieoffset"] = float(value)
        elif key == "BASEBPM":
            result["basebpm"] = float(value)
        elif key == "REQUEST":
            if "requests" not in result:
                result["requests"] = []
            result["requests"].append(value)
    return Metadata.from_dict(result)


def process_score(lines: list[tuple[str]], metadata: list[tuple[str]]) -> Score:
    processed_metadata = process_metadata(metadata)

    try:
        ticks_per_beat_request = (
            [
                int(request.split()[1])
                for request in processed_metadata.requests
                if request.startswith("ticks_per_beat")
            ]
            if processed_metadata.requests
            else []
        )
        ticks_per_beat = ticks_per_beat_request[0]
    except IndexError:
        logger.warning("No ticks_per_beat request found, defaulting to 480.")
        ticks_per_beat = 480

    bar_lengths: list[tuple[int, float]] = []
    for header, data in lines:
        if len(header) == 5 and header.endswith("02") and header.isdigit():
            bar_lengths.append((int(header[0:3]), float(data)))

    if len(bar_lengths) == 0:
        logger.warning(
            "No bar lengths found, adding default 4/4 time signature (#00002:4)..."
        )
        bar_lengths.append((0, 4.0))

    sorted_bar_lengths = sorted(bar_lengths, key=lambda x: x[0])

    ticks = 0

    bars = list(
        reversed(
            [
                (
                    measure,
                    int(beats * ticks_per_beat),
                    ticks := ticks
                    + int(
                        (measure - sorted_bar_lengths[i - 1][0])
                        * sorted_bar_lengths[i - 1][1]
                        * ticks_per_beat
                        if i > 0
                        else 0
                    ),
                )
                for i, (measure, beats) in enumerate(sorted_bar_lengths)
            ]
        )
    )

    def to_tick(measure: int, i: int, total: int) -> int:
        bar = next(bar for bar in bars if measure >= bar[0])
        if not bar:
            raise ValueError(f"Measure {measure} is out of range.")
        (bar_measure, ticks_per_measure, ticks) = bar

        return (
            ticks
            + (measure - bar_measure) * ticks_per_measure
            + (i * ticks_per_measure) // total
        )

    def fix_til_tick(measure: int, ticks_in_measure: int) -> int:
        bar = next(bar for bar in bars if measure >= bar[0])
        if not bar:
            raise ValueError(f"Measure {measure} is out of range.")
        (bar_measure, ticks_per_measure, ticks) = bar

        return ticks + (measure - bar_measure) * ticks_per_measure + ticks_in_measure

    bpm_map = {}
    bpm_change_objects = []
    til_map = {}
    tils = []  # ハイスピに対応
    tap_notes = []
    directional_notes = []
    slide_streams = defaultdict(list)
    guide_streams = defaultdict(list)  # ガイドに対応

    til_data_index = 0
    current_til_id: str = None
    for header, data in lines:
        if len(header) == 5 and header.startswith("BPM"):
            bpm_map[header[3:]] = float(data)
        elif header == "HISPEED":
            current_til_id = til_map.get(data)
            if not current_til_id:
                raise KeyError(
                    f"HISPEED {data} is not valid ({', '.join(til_map.keys())})"
                )
        elif len(header) == 5 and header.endswith("08"):
            bpm_change_objects += to_raw_objects(header, data, to_tick)
        elif len(header) == 5 and header[3] == "1":
            tap_notes += to_note_objects(header, data, current_til_id, to_tick)
        elif len(header) == 6 and header[3] == "3":
            channel = header[5]
            slide_streams[channel] += to_note_objects(
                header, data, current_til_id, to_tick
            )
        elif len(header) == 5 and header[3] == "5":
            directional_notes += to_note_objects(header, data, current_til_id, to_tick)
        # ガイドに対応
        elif len(header) == 6 and header[3] == "9":
            channel = header[5]
            guide_streams[channel] += to_note_objects(
                header, data, current_til_id, to_tick
            )
        # ハイスピに対応(仮)
        elif len(header) == 5 and header.startswith("TIL"):
            til_map[header[3:]] = til_data_index
            new_til = []
            for til in data[1:-1].replace(" ", "").split(","):
                til = re.search(r"(\d+)'(\d+):(.?\d+(\.?\d+)?)", til)
                if til:
                    measure, tick, value = (
                        int(til.group(1)),
                        int(til.group(2)),
                        float(til.group(3)),
                    )
                    new_til.append((fix_til_tick(measure, tick), value))
            tils.append(new_til)
            til_data_index += 1

    slide_notes = []
    for stream in slide_streams.values():
        slide_notes += to_slides(stream)

    # ガイドに対応
    guide_notes = []
    for stream in guide_streams.values():
        guide_notes += to_slides(stream)

    bpms = [
        (tick, bpm_map[value] or 0)
        for tick, value in sorted(bpm_change_objects, key=lambda x: x[0])
    ]

    return Score(
        metadata=processed_metadata,
        taps=tap_notes,
        directionals=directional_notes,
        slides=slide_notes,
        guides=guide_notes,
        bpms=bpms,
        tils=tils,
        bar_lengths=bar_lengths,
    )


def to_slides(stream: list[Note]) -> list[list[Note]]:
    slides: list[list[Note]] = []
    current: list[Note] = None
    for note in sorted(stream, key=lambda x: x.tick):
        if not current:
            current = []
            slides.append(current)

        current.append(note)

        if note.type == 2:
            current = None
    return slides


def to_note_objects(
    header: int, data: str, current_til_id: int, to_tick: Callable[[int, int, int], int]
) -> list[Note]:
    return [
        Note(
            tick=tick,
            lane=int(header[4], 36),
            width=int(value[1], 36),
            type=int(value[0], 36),
            til=current_til_id,
        )
        for tick, value in to_raw_objects(header, data, to_tick)
    ]


def to_raw_objects(
    header: int, data: str, to_tick: Callable[[int, int, int], int]
) -> list[tuple[int, str]]:
    measure = int(header[:3])
    values = list(enumerate(re.findall(r".{2}", data)))
    return [
        (to_tick(measure, i, len(values)), value)
        for i, value in values
        if value != "00"
    ]


def load(fp: TextIO) -> Score:
    return loads(fp.read())


def loads(data: str) -> Score:
    """
    Parse SUS data into a Score object.

    :param data: The score data.
    :return: A Score object.
    """
    metadata = []
    scoredata = []
    for line in data.splitlines():
        if not line.startswith("#"):
            continue
        line = line.strip()
        match = re.match(r"^#(\w+):\s*(.*)$", line)
        if match:
            scoredata.append(match.groups())
        else:
            metadata.append(tuple(line.split(" ", 1)))

    return process_score(scoredata, metadata)
