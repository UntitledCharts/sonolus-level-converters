from dataclasses import dataclass, field
from typing import Literal, List, Union


@dataclass
class SlideStartPoint:
    beat: float
    critical: bool
    ease: Literal["outin", "out", "linear", "in", "inout"]
    judgeType: Literal["normal", "trace", "none"]
    lane: float
    size: float
    timeScaleGroup: int
    type: str = "start"


@dataclass
class SlideRelayPoint:
    beat: float
    ease: Literal["outin", "out", "linear", "in", "inout"]
    lane: float
    size: float
    timeScaleGroup: int
    type: Literal["tick", "attach"]
    critical: bool | None = None
    fake: bool = False


@dataclass
class SlideEndPoint:
    beat: float
    critical: bool
    judgeType: Literal["normal", "trace", "none"]
    lane: float
    size: float
    timeScaleGroup: int
    direction: Literal["left", "up", "right"] | None = None
    type: str = "end"


@dataclass
class Slide:
    critical: bool
    fake: bool = False  # isdummy for UntitledSekai
    connections: List[Union[SlideStartPoint, SlideRelayPoint, SlideEndPoint]] = field(
        default_factory=list
    )
    type: str = "slide"

    def append(self, slidepoint: SlideStartPoint | SlideRelayPoint | SlideEndPoint):
        self.connections.append(slidepoint)
        self.sort()

    def sort(self):
        self.connections.sort(key=lambda x: x.beat)

    def get_sus_sort_number(self) -> int:
        return 4


def validate_slide_dict_values(data: dict) -> tuple | None:
    if not isinstance(data, dict):
        return data, "Expected a dictionary for Slide"

    found_start = False
    found_end = False

    if "connections" in data:
        if not isinstance(data["connections"], list):
            return data, "'connections' should be a list"
        if len(data["connections"]) == 0:
            return data, "'connections' can't be empty"
        for idx, item in enumerate(data["connections"]):
            if not isinstance(item, dict):
                return item, f"Item {idx} in 'connections' should be a dictionary"
            if "type" in item and item["type"] not in [
                "start",
                "tick",
                "attach",
                "end",
            ]:
                return item, f"Item {idx} in 'connections' has an invalid 'type' value"
            if item["type"] == "end":
                if found_end:
                    return data, f"Slide has more than 1 end."
                else:
                    found_end = True
            if item["type"] == "start":
                if found_start:
                    return data, f"Slide has more than 1 start."
                else:
                    found_start = True
            if "beat" not in item or not isinstance(item["beat"], (int, float)):
                return (
                    item,
                    f"Item {idx} in 'connections' is missing or has an invalid 'beat'",
                )
            if "lane" not in item or not isinstance(item["lane"], (int, float)):
                return (
                    item,
                    f"Item {idx} in 'connections' is missing or has an invalid 'lane'",
                )
            if "size" not in item or not isinstance(item["size"], (int, float)):
                return (
                    item,
                    f"Item {idx} in 'connections' is missing or has an invalid 'size'",
                )
            if "timeScaleGroup" not in item or not isinstance(
                item["timeScaleGroup"], int
            ):
                return (
                    item,
                    f"Item {idx} in 'connections' is missing or has an invalid 'timeScaleGroup'",
                )
            if (
                "critical" not in item
                or (
                    not isinstance(item["critical"], bool)
                    and item["type"] in ["start", "end"]
                )
                or (
                    item["critical"] not in [True, False, None]
                    and item["type"] in ["tick", "attach"]
                )
            ):
                return (
                    item,
                    f"Item {idx} in 'connections' has an invalid 'critical' value",
                )
            if item["type"] != "end":
                if "ease" not in item or item["ease"] not in [
                    "outin",
                    "out",
                    "linear",
                    "in",
                    "inout",
                ]:
                    return (
                        item,
                        f"Item {idx} in 'connections' has an invalid 'ease' value",
                    )
            if "judgeType" in item and item["judgeType"] not in [
                "normal",
                "trace",
                "none",
            ]:
                return (
                    item,
                    f"Item {idx} in 'connections' has an invalid 'judgeType' value",
                )
            if "direction" in item and item["direction"] not in [
                "left",
                "right",
                "up",
                None,
            ]:
                return (
                    item,
                    f"Item {idx} in 'connections' has an invalid 'direction' value",
                )
    else:
        return data, "Missing connections in Slide."

    if "critical" in data and not isinstance(data["critical"], bool):
        return data, "'critical' should be a boolean"
    if "fake" in data and not isinstance(data["fake"], bool):
        return data, "'fake' should be a boolean"
    if "type" in data and not isinstance(data["type"], str):
        return data, "'type' should be a string"

    return None
