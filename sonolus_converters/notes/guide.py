from dataclasses import dataclass, field
from typing import Literal, List


@dataclass
class GuidePoint:
    beat: float
    ease: Literal["outin", "out", "linear", "in", "inout"]
    lane: float
    size: float
    timeScaleGroup: float


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
