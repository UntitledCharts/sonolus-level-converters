from dataclasses import dataclass
from typing import Literal


@dataclass
class Damage:
    beat: float
    lane: float
    size: float
    timeScaleGroup: float
    type: str = "damage"

    def get_sus_sort_number(self) -> int:
        return 3


@dataclass
class Single:
    beat: float
    critical: bool
    lane: float
    size: float
    timeScaleGroup: float
    trace: bool
    direction: Literal["left", "up", "right"] | None = None
    type: str = "single"

    def get_sus_sort_number(self) -> int:
        return 3
