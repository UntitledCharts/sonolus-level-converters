import io
import os
from pathlib import Path
from typing import IO, Literal

from ..notes.score import Score
from .. import sus
from .detector import detect
from . import chart_cyanvas, pjsekai


LevelDataType = Literal["base", "chcy", "pysekai"]
LevelDataSource = os.PathLike | IO[bytes] | IO[str] | bytes | bytearray | str


def _read_source(data: LevelDataSource) -> bytes:
    if isinstance(data, (bytes, bytearray, memoryview)):
        return bytes(data)

    if isinstance(data, (os.PathLike, Path)):
        with open(data, "rb") as fp:
            return fp.read()

    if isinstance(data, str):
        path = Path(data)
        if path.exists():
            with open(path, "rb") as fp:
                return fp.read()
        return data.encode("utf-8")

    raw = data.read()
    if isinstance(raw, str):
        return raw.encode("utf-8")
    return raw


def _get_loader(level_data_type: LevelDataType):
    if level_data_type in ("base", "chcy"):
        return chart_cyanvas.load
    return pjsekai.load


def load(
    data: LevelDataSource,
    *,
    level_data_type: LevelDataType | None = None,
) -> Score:
    raw = _read_source(data)
    resolved_type = level_data_type or detect(raw)
    if resolved_type is None:
        try:
            resolved_type = detect(raw.decode("utf-8"), skip_gzip=True)
        except UnicodeDecodeError:
            pass
    if resolved_type is None:
        raise ValueError("Unable to detect LevelData type")

    loader = _get_loader(resolved_type)
    with io.BufferedReader(io.BytesIO(raw)) as fp:
        return loader(fp)


def to_sus(
    path: os.PathLike | str,
    data: LevelDataSource,
    *,
    level_data_type: LevelDataType | None = None,
    allow_layers: bool = False,
    allow_extended_lanes: bool = False,
    delete_damage: bool = True,
):
    score = load(data, level_data_type=level_data_type)
    return sus.export(
        path,
        score,
        allow_layers=allow_layers,
        allow_extended_lanes=allow_extended_lanes,
        delete_damage=delete_damage,
    )
