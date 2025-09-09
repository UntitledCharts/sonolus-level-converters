from dataclasses import dataclass
from typing import Literal


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

    def get_sort_number(self) -> int:
        return 3
