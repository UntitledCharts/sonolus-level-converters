from dataclasses import dataclass, field
from typing import Literal, List, Union


@dataclass
class SlideStartPoint:
    beat: float
    critical: bool
    ease: Literal["in", "out", "linear"]
    judgeType: Literal["normal", "trace", "none"]
    lane: float
    size: float
    timeScaleGroup: float
    type: str = "start"


@dataclass
class SlideRelayPoint:
    beat: float
    ease: Literal["in", "out", "linear"]
    lane: float
    size: float
    timeScaleGroup: float
    type: Literal["tick", "attach"]
    critical: bool | None = None


@dataclass
class SlideEndPoint:
    beat: float
    critical: bool
    judgeType: Literal["normal", "trace", "none"]
    lane: float
    size: float
    timeScaleGroup: float
    direction: Literal["left", "up", "right"] | None = None
    type: str = "end"


@dataclass
class Slide:
    critical: bool
    connections: List[Union[SlideStartPoint, SlideRelayPoint, SlideEndPoint]] = field(
        default_factory=list
    )
    type: str = "slide"

    def append(self, slidepoint: SlideStartPoint | SlideRelayPoint | SlideEndPoint):
        self.connections.append(slidepoint)
        self.connections.sort(key=lambda x: x.beat)

    def get_sort_number(self) -> int:
        return 4
