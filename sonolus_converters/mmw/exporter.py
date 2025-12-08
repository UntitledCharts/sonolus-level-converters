from ..notes import Score

from typing import Union
from pathlib import Path
import io


def export(path: Union[str, Path, io.BytesIO], score: Score):
    raise NotImplementedError
    if isinstance(path, (str, Path)):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb", encoding="utf-8") as f:
            ...
    elif isinstance(path, io.BytesIO):
        path.write(bytes, (not string))
        path.seek(0)
    else:
        raise TypeError(f"Unsupported path type: {type(path)}")
