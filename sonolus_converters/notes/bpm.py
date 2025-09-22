from dataclasses import dataclass


@dataclass
class Bpm:
    beat: float
    bpm: float
    type: str = "bpm"

    def get_sus_sort_number(self) -> int:
        return 1


def validate_bpm_dict_values(data: dict) -> tuple | None:
    if not isinstance(data, dict):
        return data, "Expected a dictionary for BPM"
    if "beat" not in data or not isinstance(data["beat"], (int, float)):
        return data, "'beat' is missing or invalid"
    if "bpm" not in data or not isinstance(data["bpm"], (int, float)):
        return data, "'bpm' is missing or invalid"
    if "type" in data and not isinstance(data["type"], str):
        return data, "'type' should be a string"
    return None
