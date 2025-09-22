from dataclasses import dataclass, field
from typing import List


@dataclass
class TimeScalePoint:
    beat: float
    timeScale: float


@dataclass
class TimeScaleGroup:
    changes: List[TimeScalePoint] = field(default_factory=list)
    type: str = "timeScaleGroup"

    def append(self, time_scale: TimeScalePoint):
        self.changes.append(time_scale)

    def insert(self, index: int, time_scale: TimeScalePoint):
        self.changes.insert(index, time_scale)

    def get_sus_sort_number(self) -> int:
        return 2


def validate_timescale_dict_values(data: dict) -> tuple | None:
    if not isinstance(data, dict):
        return data, "Expected a dictionary for TimeScaleGroup"

    if "changes" in data:
        if not isinstance(data["changes"], list):
            return data, "'changes' should be a list"
        for idx, item in enumerate(data["changes"]):
            if not isinstance(item, dict):
                return item, f"Item {idx} in 'changes' should be a dictionary"
            if not all(k in item for k in ["beat", "timeScale"]):
                return (
                    item,
                    f"Item {idx} in 'changes' is missing required keys ('beat', 'timeScale')",
                )
            if not isinstance(item["beat"], (int, float)):
                return (
                    item,
                    f"Item {idx} in 'changes' has an invalid 'beat' value, expected a number",
                )
            if not isinstance(item["timeScale"], (int, float)):
                return (
                    item,
                    f"Item {idx} in 'changes' has an invalid 'timeScale' value, expected a number",
                )
    else:
        return data, "Missing changes in TimeScaleGroup"

    if "type" in data and not isinstance(data["type"], str):
        return data, "'type' should be a string"

    return None
