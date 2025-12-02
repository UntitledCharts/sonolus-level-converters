from dataclasses import dataclass
from typing import Literal


@dataclass(kw_only=True)
class Skill:
    # lane: int = 0
    # width: int = 1
    beat: float
    type: Literal["skill"] = "skill"

    def get_sus_sort_number(self) -> int:
        return 3


@dataclass(kw_only=True)
class FeverStart:
    # lane: int = 15
    # width: int = 1
    beat: float
    type: Literal["fever1"] = "fever1"

    def get_sus_sort_number(self) -> int:
        return 3


@dataclass(kw_only=True)
class FeverEnd:
    # lane: int = 15
    # width: int = 1
    beat: float
    type: Literal["fever2"] = "fever2"

    def get_sus_sort_number(self) -> int:
        return 3


@dataclass(kw_only=True)
class Single:
    beat: float
    critical: bool | None = None
    lane: float
    size: float
    fake: bool = False  # isdummy for UntitledSekai
    timeScaleGroup: int
    trace: bool | None = None
    direction: Literal["left", "up", "right"] | None = None
    type: Literal["single", "damage"] = "single"

    def get_sus_sort_number(self) -> int:
        return 3


def validate_event_dict_values(data: dict) -> tuple | None:
    if not isinstance(data, dict):
        return data, "Expected a dictionary for FeverStart/FeverEnd/Skill"
    if (
        "type" in data
        and not isinstance(data["type"], str)
        and not data["type"] in ["skill", "fever1", "fever2"]
    ):
        return data, "'type' should be a string"
    if "beat" not in data or not isinstance(data["beat"], (int, float)):
        return data, "'beat' is missing or invalid"
    return None


def validate_single_dict_values(data: dict) -> tuple | None:
    if not isinstance(data, dict):
        return data, "Expected a dictionary for Single"
    if (
        "type" in data
        and not isinstance(data["type"], str)
        and not data["type"] in ["damage", "single"]
    ):
        return data, "'type' should be a string"
    if "beat" not in data or not isinstance(data["beat"], (int, float)):
        return data, "'beat' is missing or invalid"
    if data["type"] == "single":
        if "critical" not in data or not isinstance(data["critical"], bool):
            return data, "'critical' is missing or invalid"
    if "lane" not in data or not isinstance(data["lane"], (int, float)):
        return data, "'lane' is missing or invalid"
    if "size" not in data or not isinstance(data["size"], (int, float)):
        return data, "'size' is missing or invalid"
    if "timeScaleGroup" not in data or not isinstance(data["timeScaleGroup"], int):
        return data, "'timeScaleGroup' is missing or invalid"
    if data["type"] == "single":
        if "trace" not in data or not isinstance(data["trace"], bool):
            return data, "'trace' should be a boolean"
        if "direction" in data and data["direction"] not in [
            "left",
            "up",
            "right",
            None,
        ]:
            return data, "'direction' has an invalid value"
    if "fake" in data and not isinstance(data["fake"], bool):
        return data, "'fake' should be a boolean"
    return None
