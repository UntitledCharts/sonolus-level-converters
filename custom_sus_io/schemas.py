"""
MIT License

Copyright (c) 2021 mkpoli

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

from dataclasses import dataclass, field
from dataclasses_json import dataclass_json, LetterCase, Undefined
from typing import Optional

from dataclasses_json.cfg import config


def exclude_none():
    return field(default=None, metadata=config(exclude=lambda x: x is None))


@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class Metadata:
    title: Optional[str] = exclude_none()
    subtitle: Optional[str] = exclude_none()
    artist: Optional[str] = exclude_none()
    genre: Optional[str] = exclude_none()
    designer: Optional[str] = exclude_none()
    difficulty: Optional[str] = exclude_none()
    playlevel: Optional[str] = exclude_none()
    songid: Optional[str] = exclude_none()
    wave: Optional[str] = exclude_none()
    waveoffset: Optional[float] = exclude_none()
    jacket: Optional[str] = exclude_none()
    background: Optional[str] = exclude_none()
    movie: Optional[str] = exclude_none()
    movieoffset: Optional[float] = exclude_none()
    basebpm: Optional[float] = exclude_none()
    requests: Optional[list[str]] = exclude_none()


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class Note:
    tick: int
    lane: int
    width: int
    type: int


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class Score:
    metadata: Metadata
    taps: list[Note]
    directionals: list[Note]
    slides: list[list[Note]]
    guides: list[list[Note]]
    bpms: list[tuple[int, float]]
    bar_lengths: list[tuple[int, float]]
    tils: list[tuple[int, float]]


@dataclass
class BarLength:
    start_tick: int
    measure: int
    value: float
