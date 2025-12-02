from dataclasses import dataclass, field
from typing import Literal, List


@dataclass
class GuidePoint:
    beat: float
    ease: Literal["outin", "out", "linear", "in", "inout"]
    lane: float
    size: float
    timeScaleGroup: int


@dataclass
class Guide:
    color: Literal[
        "neutral", "red", "green", "blue", "yellow", "purple", "cyan", "black"
    ]
    fade: Literal["in", "out", "none"]
    midpoints: List[GuidePoint] = field(default_factory=list)
    type: str = "guide"

    def append(self, guidepoint: GuidePoint):
        self.midpoints.append(guidepoint)
        self.sort()

    def sort(self):
        self.midpoints.sort(key=lambda x: x.beat)

    def get_sus_sort_number(self) -> int:
        return 5


def validate_guide_dict_values(data: dict) -> tuple | None:
    if not isinstance(data, dict):
        return data, "Expected a dictionary for Guide"

    if "color" not in data or data["color"] not in [
        "neutral",
        "red",
        "green",
        "blue",
        "yellow",
        "purple",
        "cyan",
        "black",
    ]:
        return data, "'color' is missing or invalid"
    if "fade" not in data or data["fade"] not in ["in", "out", "none"]:
        return data, "'fade' is missing or invalid"
    if "type" in data and not isinstance(data["type"], str):
        return data, "'type' should be a string"

    if "midpoints" in data:
        if not isinstance(data["midpoints"], list):
            return data, "'midpoints' should be a list"
        if len(data["midpoints"]) == 0:
            return data, "'midpoints' can't be empty"
        for idx, item in enumerate(data["midpoints"]):
            if not isinstance(item, dict):
                return item, f"Item {idx} in 'midpoints' should be a dictionary"
            if "beat" not in item or not isinstance(item["beat"], (int, float)):
                return (
                    item,
                    f"Item {idx} in 'midpoints' is missing or has an invalid 'beat'",
                )
            if "ease" not in item or item["ease"] not in [
                "outin",
                "out",
                "linear",
                "in",
                "inout",
            ]:
                return item, f"Item {idx} in 'midpoints' has an invalid 'ease' value"
            if "lane" not in item or not isinstance(item["lane"], (int, float)):
                return (
                    item,
                    f"Item {idx} in 'midpoints' is missing or has an invalid 'lane'",
                )
            if "size" not in item or not isinstance(item["size"], (int, float)):
                return (
                    item,
                    f"Item {idx} in 'midpoints' is missing or has an invalid 'size'",
                )
            if "timeScaleGroup" not in item or not isinstance(
                item["timeScaleGroup"], int
            ):
                return (
                    item,
                    f"Item {idx} in 'midpoints' is missing or has an invalid 'timeScaleGroup'",
                )
    else:
        return data, f"Missing midpoints."

    return None
