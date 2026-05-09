import base64
import gzip
import json
import io


def detect(data: bytes) -> bool:
    try:
        decoded = base64.b64decode(data, validate=True)
    except Exception:
        return False

    if decoded[:2] != b"\x1f\x8b":
        return False

    try:
        with gzip.GzipFile(fileobj=io.BytesIO(decoded), mode="rb") as gz:
            parsed = json.loads(gz.read())
    except (gzip.BadGzipFile, json.JSONDecodeError, EOFError):
        return False

    return "NoteList" in parsed and "MusicScoreEventDataList" in parsed
