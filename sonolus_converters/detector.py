from typing import Union, IO, Tuple, Literal
import os
import gzip
import json
import io
from . import sus, mmws, usc, LevelData


def detect(data: Union[os.PathLike, IO[bytes], bytes, str]) -> Union[
    Tuple[Literal["sus"], Literal[""]],
    Tuple[Literal["mmw"], Literal["base", "chcy", "unch"]],
    Tuple[Literal["usc"], Literal["v1", "v2"]],
    Tuple[
        Literal["lvd"],
        Literal[
            "base",
            "chcy",
            "pysekai",
            "compress_base",
            "compress_chcy",
            "compress_pysekai",
        ],
    ],
    None,
]:
    """Parse the data and determine the format of the score

    :returns: ``(format, specifier)`` if detected, else ``None``.
    :rtype: tuple[str, str] | None
    """
    if isinstance(data, (os.PathLike, str)):
        with open(data, "rb") as f:
            data = f.read()
    elif isinstance(data, IO):
        data = data.read()
    elif isinstance(data, memoryview):
        data = data.tobytes()

    # Check for formats with binary data and magic number first
    # Gzip data
    GZIP_MAGIC_NUM = b"\x1f\x8b"
    if data[:2] == GZIP_MAGIC_NUM:
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(data), mode="rb", mtime=0) as gz:
                json_data = json.load(gz)
                format_spec = LevelData.detect(
                    json_data, skip_gzip=True, skip_json=True
                )
                if format_spec is not None:
                    return ("lvd", "compress_" + format_spec)
        except (gzip.BadGzipFile, json.JSONDecodeError):
            pass
    # MMW data
    format_spec = mmws.detect(data)
    if format_spec:
        return ("mmw", format_spec)

    # Binary dection over
    try:
        data = data.decode()
    except UnicodeDecodeError:
        return
    # uncompressed Leveldata
    format_spec = LevelData.detect(data, skip_gzip=True)
    if format_spec:
        return ("lvd", format_spec)
    # usc
    format_spec = usc.detect(data)
    if format_spec:
        return ("usc", format_spec)
    # sus
    format_spec = sus.detect(data)
    if format_spec is not None:
        return ("sus", format_spec)
