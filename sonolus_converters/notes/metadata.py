from dataclasses import dataclass


@dataclass
class MetaData:
    title: str
    artist: str
    designer: str
    waveoffset: float
    requests: list


def validate_metadata_dict_values(data: dict) -> tuple | None:
    if not isinstance(data, dict):
        return data, "Expected a dictionary for MetaData"
    if "title" not in data or not isinstance(data["title"], str):
        return data, "'title' is missing or invalid"
    if "artist" not in data or not isinstance(data["artist"], str):
        return data, "'artist' is missing or invalid"
    if "designer" not in data or not isinstance(data["designer"], str):
        return data, "'designer' is missing or invalid"
    if "waveoffset" not in data or not isinstance(data["waveoffset"], (int, float)):
        return data, "'waveoffset' is missing or invalid"
    if "requests" not in data or not isinstance(data["requests"], list):
        return data, "'requests' should be a list"
    if any(type(i) != str for i in data["requests"]):
        return data, "Some elements in 'requests' are not strings"
    return None
