"""holodori-only timeline events. holodori marks the fever charge and fever windows with a start
and an end each, where sekai has just the two open-ended FeverChance/FeverStart markers.
"""

from dataclasses import dataclass
from typing import Literal

from .single import FeverChance, FeverStart, Skill


@dataclass(kw_only=True)
class HolodoriSkill:
    beat: float
    slot: int  # deck position (1-5) whose special skill fires here
    type: Literal["holodoriSkill"] = "holodoriSkill"

    def get_sus_sort_number(self) -> int:
        return 3


@dataclass(kw_only=True)
class HolodoriChargeStart:
    beat: float
    type: Literal["holodoriChargeStart"] = "holodoriChargeStart"

    def get_sus_sort_number(self) -> int:
        return 3


@dataclass(kw_only=True)
class HolodoriChargeEnd:
    beat: float
    type: Literal["holodoriChargeEnd"] = "holodoriChargeEnd"

    def get_sus_sort_number(self) -> int:
        return 3


@dataclass(kw_only=True)
class HolodoriFeverStart:
    beat: float
    type: Literal["holodoriFeverStart"] = "holodoriFeverStart"

    def get_sus_sort_number(self) -> int:
        return 3


@dataclass(kw_only=True)
class HolodoriFeverEnd:
    beat: float
    type: Literal["holodoriFeverEnd"] = "holodoriFeverEnd"

    def get_sus_sort_number(self) -> int:
        return 3


HolodoriEvent = (
    HolodoriSkill
    | HolodoriChargeStart
    | HolodoriChargeEnd
    | HolodoriFeverStart
    | HolodoriFeverEnd
)

HOLODORI_EVENTS = (
    HolodoriSkill,
    HolodoriChargeStart,
    HolodoriChargeEnd,
    HolodoriFeverStart,
    HolodoriFeverEnd,
)

HOLODORI_EVENT_TYPES = frozenset(event.type for event in HOLODORI_EVENTS)


def convert_holodori_events(notes: list) -> list:
    """Replace holodori events with their sekai equivalents, for exporting to a format that has
    skill/fever but no section ends. ChargeEnd and FeverEnd are dropped."""
    converted = []
    skill_beats: set[float] = set()
    for note in notes:
        if isinstance(note, HolodoriSkill):
            # Skill has no slot, so members firing on the same beat collapse into one
            if note.beat not in skill_beats:
                skill_beats.add(note.beat)
                converted.append(Skill(beat=note.beat))
        elif isinstance(note, HolodoriChargeStart):
            converted.append(FeverChance(beat=note.beat))
        elif isinstance(note, HolodoriFeverStart):
            converted.append(FeverStart(beat=note.beat))
        elif not isinstance(note, (HolodoriChargeEnd, HolodoriFeverEnd)):
            converted.append(note)
    return converted


def validate_holodori_event_dict_values(data: dict) -> tuple | None:
    if not isinstance(data, dict):
        return data, "Expected a dictionary for a holodori event"
    if "type" in data and data["type"] not in HOLODORI_EVENT_TYPES:
        return data, "'type' has an invalid value"
    if "beat" not in data or not isinstance(data["beat"], (int, float)):
        return data, "'beat' is missing or invalid"
    if data.get("type") == HolodoriSkill.type:
        if "slot" not in data or not isinstance(data["slot"], int):
            return data, "'slot' is missing or invalid"
    return None
