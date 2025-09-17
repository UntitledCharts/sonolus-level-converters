from dataclasses import dataclass
from typing import Literal


@dataclass(kw_only=True)
class Damage:
    beat: float
    lane: float
    size: float
    fake: bool = False
    timeScaleGroup: float
    type: str = "damage"

    def get_sus_sort_number(self) -> int:
        return 3


@dataclass(kw_only=True)
class Single:
    beat: float
    critical: bool
    lane: float
    size: float
    fake: bool = False  # isdummy for UntitledSekai
    timeScaleGroup: float
    trace: bool
    direction: Literal["left", "up", "right"] | None = None
    type: str = "single"

    def get_sus_sort_number(self) -> int:
        return 3
