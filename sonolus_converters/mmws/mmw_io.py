import os
import struct
from enum import Enum, IntEnum, IntFlag, auto as enum_auto
from typing import BinaryIO, Literal, Callable
from ..notes import *

# ==== Binary IO ====
def read_cstr(f: BinaryIO, chunk_size = 1024):
    buff = bytearray()
    pos = -1
    while pos == -1:
        block = f.read(chunk_size)
        if not block:
            break
        pos = block.find(b'\0')
        if pos == -1:
            buff.extend(block)
        else:
            buff.extend(block[:pos])
            seek_back = pos + 1 - len(block)
            if seek_back:
                f.seek(seek_back, os.SEEK_CUR)
    return buff.decode()

def read_int(f: BinaryIO, bit_size: Literal[8, 16, 32, 64] = 32, signed = False):
    return int.from_bytes(f.read(bit_size // 8), 'little', signed=signed)

def read_float(f: BinaryIO, bit_size: Literal[32, 64] = 32):
    return float(struct.unpack('<f' if bit_size == 32 else '<d', f.read(bit_size // 8))[0])

def write_cstr(f: BinaryIO, value: str):
    b = value.encode()
    if b'\0' in b:
        raise ValueError('C-string cannot contain null bytes')
    f.write(b)
    f.write(b'\0')

def fill_zero(f: BinaryIO, byte_count: int):
    f.write(b"\0" * byte_count)

def write_int(f: BinaryIO, value: int, bit_size: Literal[8, 16, 32, 64] = 32, signed = False):
    byte_count = bit_size // 8
    f.write(value.to_bytes(byte_count, byteorder='little', signed=signed))

def write_float(f: BinaryIO, value: float, bit_size: Literal[32, 64] = 32):
    f.write(struct.pack('<d' if bit_size == 64 else '<f', value))

# ==== Details about mmw ====
class Signature(Enum):
    MikuMikuWorld = 'MMWS'
    MikuMikuWorld4ChartCyanvas = 'CCMMWS'
    MikuMikuWorld4UntitledChart = 'UCMMWS'

class Version:
    MikuMikuWorld = 4
    MikuMikuWorld4ChartCyanvas = 6
    MikuMikuWorld4UntitledChart = 1

    def __init__(self, uc_version = MikuMikuWorld4UntitledChart, cc_version = MikuMikuWorld4ChartCyanvas, version = MikuMikuWorld):
        self.has_skill_fever = version >= 2
        self.has_jacket = version >= 2
        self.has_address = version >= 3
        self.has_hispeed = version >= 3
        self.has_guideNote = version >= 4
        self.has_damageNote = cc_version >= 1
        self.has_laneExtension = cc_version >= 1
        self.has_fadeType = cc_version >= 2
        self.has_guideColor = cc_version >= 3
        self.has_layers = cc_version >= 4
        self.has_waypoints = cc_version >= 5
        self.has_floatLaneWidth = cc_version >= 6
        self.has_dummyNote = cc_version >= 6 and uc_version >= 1
        if uc_version:
            self.value = uc_version
        elif cc_version:
            self.value = int.from_bytes(struct.pack('<HH', version, cc_version), 'little')
        else:
            self.value = version

class NoteFlag(IntFlag):
    NONE = 0
    NOTE_CRITICAL = enum_auto()
    NOTE_FRICTION = enum_auto()
    NOTE_DUMMY    = enum_auto()

class HoldFlag(IntFlag):
    NONE = 0
    HOLD_START_HIDDEN = enum_auto()
    HOLD_END_HIDDEN   = enum_auto()
    HOLD_GUIDE        = enum_auto()
    HOLD_FAKE         = enum_auto()

class FlickType(IntEnum):
    NONE           = 0
    DEFAULT        = enum_auto()
    LEFT           = enum_auto()
    RIGHT          = enum_auto()
    FLICKTYPECOUNT = enum_auto()

class EaseType(IntEnum):
    LINEAR        = 0
    EASEIN        = enum_auto()
    EASEOUT       = enum_auto()
    EASEINOUT     = enum_auto()
    EASEOUTIN     = enum_auto()
    EASETYPECOUNT = enum_auto()

class GuideColor(IntEnum):
    NEUTRAL = 0
    RED     = enum_auto()
    GREEN   = enum_auto()
    BLUE    = enum_auto()
    YELLOW  = enum_auto()
    PURPLE  = enum_auto()
    CYAN    = enum_auto()
    BLACK   = enum_auto()
    GUIDE_COLOR_COUNT = enum_auto()

class FadeType(IntEnum):
    OUT  = 0
    NONE = enum_auto()
    IN   = enum_auto()


# ==== Conversion ====
_NotesList = list[Bpm | TimeScaleGroup | Single | Skill | FeverStart | FeverChance | Slide | Guide]

def tick_to_beat(tick: int, ticks_per_beat=480):
    return round(tick / ticks_per_beat, 6)

def beat_to_tick(beat: float, ticks_per_beat=480):
    return int(round(beat * ticks_per_beat))

def to_usc_lane(mmw_lane: int | float, width: int | float):
    return mmw_lane - 6 + width / 2

def to_mmw_lane[T](usc_lane: float, size: float, result_t: Callable[[float], T] = float) -> T:
    match result_t(0):
        case int(0):
            return result_t(usc_lane + 6 - size)
        case float(0):
            return result_t(usc_lane + 6 - size)
        case _:
            raise ValueError('Unknown result type')

def width_to_size(width: int | float):
    return width / 2

def size_to_width[T](size: float, result_t: Callable[[float], T] = float) -> T:
    return result_t(size * 2)

def flick_to_direction(flick_type: int):
    match flick_type:
        case FlickType.NONE: return None
        case FlickType.DEFAULT: return 'up'
        case FlickType.LEFT: return 'left'
        case FlickType.RIGHT: return 'right'
        case _: raise ValueError(f'Unknown flick type: {flick_type}')
        
def direction_to_flick(direction: Literal['up', 'left', 'right'] | None):
    match direction:
        case None: return FlickType.NONE
        case 'up': return FlickType.DEFAULT
        case 'left': return FlickType.LEFT
        case 'right': return FlickType.RIGHT
        case _: raise ValueError(f'Unknown direction type: {direction}')
        
def ease_num_to_ease(ease_num: int):
    match ease_num:
        case EaseType.LINEAR: return 'linear'
        case EaseType.EASEIN: return 'in'
        case EaseType.EASEOUT: return 'out'
        case EaseType.EASEINOUT: return 'inout'
        case EaseType.EASEOUTIN: return 'outin'
        case _: raise ValueError(f'Unknown ease type: {ease_num}')

def ease_to_ease_num(ease: Literal['outin', 'out', 'linear', 'in', 'inout']):
    match ease:
        case 'linear': return EaseType.LINEAR
        case 'in': return EaseType.EASEIN
        case 'out': return EaseType.EASEOUT
        case 'inout': return EaseType.EASEINOUT
        case 'outin': return EaseType.EASEOUTIN
        case _: raise ValueError(f'Unknown ease string: {ease}')

def guide_color_to_color(guide_color: int):
    match guide_color:
        case 0: return 'neutral'
        case 1: return 'red'
        case 2: return 'green'
        case 3: return 'blue'
        case 4: return 'yellow'
        case 5: return 'purple'
        case 6: return 'cyan'
        case 7: return 'black'
        case _: raise ValueError(f'Unknown guide color index: {guide_color}')


def color_to_guide_color(color: Literal['neutral', 'red', 'green', 'blue', 'yellow', 'purple', 'cyan', 'black']):
    match color:
        case 'neutral': return 0
        case 'red': return 1
        case 'green': return 2
        case 'blue': return 3
        case 'yellow': return 4
        case 'purple': return 5
        case 'cyan': return 6
        case 'black': return 7
        case _: raise ValueError(f'Unknown guide color: {color}')

def fade_type_to_fade(fade_type: int):
    match fade_type:
        case 0: return 'out'
        case 1: return 'none'
        case 2: return 'in'
        case _: raise ValueError(f'Unknown fade type index: {fade_type}')

def fade_to_fade_type(fade: Literal['out', 'none', 'in']) -> int:
    match fade:
        case 'out': return 0
        case 'none': return 1
        case 'in': return 2
        case _: raise ValueError(f'Unknown fade type: {fade}')

class NoteGroups:
    def __init__(self, notes: _NotesList):
        self.groups: dict[type, list] = {}
        for note in notes:
            self.groups.setdefault(type(note), []).append(note)

    def by[T](self, object_type: type[T]) -> list[T]:
        return self.groups.get(object_type, [])