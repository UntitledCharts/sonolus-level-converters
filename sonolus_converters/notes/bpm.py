from dataclasses import dataclass


@dataclass
class Bpm:
    beat: float
    bpm: float
    type: str = "bpm"

    def get_sort_number(self) -> int:
        return 1
