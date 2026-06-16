from dataclasses import dataclass


@dataclass
class Volume:
    beat: float
    volume: float
    type: str = "volume"

    def get_sus_sort_number(self) -> int:
        return 1


def validate_volume_dict_values(data: dict) -> tuple | None:
    if not isinstance(data, dict):
        return data, "Expected a dictionary for Volume"
    if "beat" not in data or not isinstance(data["beat"], (int, float)):
        return data, "'beat' is missing or invalid"
    if "volume" not in data or not isinstance(data["volume"], (int, float)):
        return data, "'volume' is missing or invalid"
    if "type" in data and not isinstance(data["type"], str):
        return data, "'type' should be a string"
    return None
