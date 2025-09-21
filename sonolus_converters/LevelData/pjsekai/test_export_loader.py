import io
import json
import gzip
from pathlib import Path

from .exporter import export
from .loader import load
from ...notes.bpm import Bpm
from ...notes.single import Single
from ...notes.slide import Slide, SlideStartPoint, SlideRelayPoint, SlideEndPoint
from ...notes.guide import Guide, GuidePoint
from ...notes.metadata import MetaData
from ...notes.score import Score

metadata = MetaData(
    title="Test",
    artist="Test",
    designer="Test",
    waveoffset=0,
    requests="ticks_per_beat 480",
)
notes = [
    Bpm(beat=0, bpm=160.0),
    Single(
        beat=1.0,
        critical=False,
        lane=1,
        size=1,
        trace=False,
        direction=None,
        timeScaleGroup=0,
    ),  # Tap
    Single(
        beat=2.0,
        critical=True,
        lane=2,
        size=1,
        trace=False,
        direction=None,
        timeScaleGroup=0,
    ),  # Critical Tap
    Single(
        beat=3.0,
        critical=False,
        lane=3,
        size=1,
        trace=True,
        direction=None,
        timeScaleGroup=0,
    ),  # Trace Tap
    Single(
        beat=4.0,
        critical=False,
        lane=1,
        size=1,
        trace=False,
        direction="left",
        timeScaleGroup=0,
    ),  # Flick
    # Slide
    Slide(
        critical=True,
        connections=[
            SlideStartPoint(
                beat=5.0,
                lane=1,
                size=1,
                timeScaleGroup=0,
                critical=True,
                ease="in",
                judgeType="trace",
            ),
            SlideRelayPoint(
                beat=5.5,
                lane=2,
                size=1,
                timeScaleGroup=0,
                type="tick",
                critical=False,
                ease="linear",
            ),
            SlideEndPoint(
                beat=6.0,
                lane=3,
                size=1,
                timeScaleGroup=0,
                critical=True,
                judgeType="trace",
                direction="right",
            ),
        ],
    ),
    # Guide
    Guide(
        color="yellow",
        fade=0.5,
        midpoints=[
            GuidePoint(beat=7.0, ease="out", lane=1, size=1, timeScaleGroup=0),
            GuidePoint(beat=7.5, ease="linear", lane=2, size=1, timeScaleGroup=0),
            GuidePoint(beat=8.0, ease="in", lane=3, size=1, timeScaleGroup=0),
        ],
    ),
]
score = Score(metadata=metadata, notes=notes)


def test_export_import_roundtrip(score):
    buf = io.BytesIO()
    export(buf, score, as_compressed=True)
    buf.seek(0)

    loaded_score = load(buf)

    orig_dict = score.__dict__.copy()
    loaded_dict = loaded_score.__dict__.copy()
    print("\033[1mOriginal:\033[0m", orig_dict)
    print("\033[1mLoaded:\033[0m", loaded_dict)
    if json.dumps(orig_dict, default=str) == json.dumps(loaded_dict, default=str):
        print("scores are equal")
    else:
        print("scores are not equal noob")


if __name__ == "__main__":
    test_export_import_roundtrip(score)
