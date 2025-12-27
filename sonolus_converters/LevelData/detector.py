import io
import gzip
import json
from collections import abc
from typing import Literal


# Probably move these to their individual module?
def _base_engine_archetypes():
    return {
        "Initialization",
        "Stage",
        "NormalTapNote",
        "CriticalTapNote",
        "NormalFlickNote",
        "CriticalFlickNote",
        "NormalTraceNote",
        "CriticalTraceNote",
        "NormalTraceFlickNote",
        "CriticalTraceFlickNote",
        "NormalSlideStartNote",
        "CriticalSlideStartNote",
        "NormalSlideEndNote",
        "CriticalSlideEndNote",
        "NormalSlideEndFlickNote",
        "CriticalSlideEndFlickNote",
        "IgnoredSlideTickNote",
        "NormalSlideTickNote",
        "CriticalSlideTickNote",
        "HiddenSlideTickNote",
        "NormalAttachedSlideTickNote",
        "CriticalAttachedSlideTickNote",
        "NormalSlideConnector",
        "CriticalSlideConnector",
        "SimLine",
        # Base trace implementation
        "NormalSlideTraceNote",
        "CriticalSlideTraceNote",
        "NormalSlideEndTraceNote",
        "CriticalSlideEndTraceNote",
        "NormalActiveSlideConnector",
        "CriticalActiveSlideConnector",
    }


def _chcy_engine_archetypes():
    return {
        "Initialization",
        "Stage",
        "NormalTapNote",
        "CriticalTapNote",
        "NormalFlickNote",
        "CriticalFlickNote",
        "NormalTraceNote",
        "CriticalTraceNote",
        "NormalTraceFlickNote",
        "CriticalTraceFlickNote",
        "NormalSlideStartNote",
        "CriticalSlideStartNote",
        "NormalSlideEndNote",
        "CriticalSlideEndNote",
        "NormalSlideEndFlickNote",
        "CriticalSlideEndFlickNote",
        "IgnoredSlideTickNote",
        "NormalSlideTickNote",
        "CriticalSlideTickNote",
        "HiddenSlideTickNote",
        "NormalAttachedSlideTickNote",
        "CriticalAttachedSlideTickNote",
        "NormalSlideConnector",
        "CriticalSlideConnector",
        "SimLine",
        # Chcy trace implementation
        "NormalTraceSlideStartNote",
        "CriticalTraceSlideStartNote",
        "NormalTraceSlideEndNote",
        "CriticalTraceSlideEndNote",
        "NonDirectionalTraceFlickNote",
        # Chcy extend
        "DamageNote",
        "HiddenSlideStartNote",
        "TimeScaleGroup",
        "TimeScaleChange",
        "Guide",
    }


def _pysekai_engine_archetypes():
    return {
        "#TIMESCALE_CHANGE",
        "#TIMESCALE_GROUP",
        "Initialization",
        "Stage",
        "SimLine",
        "Connector",
        "NormalTapNote",
        "CriticalTapNote",
        "NormalFlickNote",
        "CriticalFlickNote",
        "NormalTraceNote",
        "CriticalTraceNote",
        "NormalTraceFlickNote",
        "CriticalTraceFlickNote",
        "NormalReleaseNote",
        "CriticalReleaseNote",
        "NormalHeadTapNote",
        "CriticalHeadTapNote",
        "NormalHeadFlickNote",
        "CriticalHeadFlickNote",
        "NormalHeadTraceNote",
        "CriticalHeadTraceNote",
        "NormalHeadTraceFlickNote",
        "CriticalHeadTraceFlickNote",
        "NormalHeadReleaseNote",
        "CriticalHeadReleaseNote",
        "NormalTailTapNote",
        "CriticalTailTapNote",
        "NormalTailFlickNote",
        "CriticalTailFlickNote",
        "NormalTailTraceNote",
        "CriticalTailTraceNote",
        "NormalTailTraceFlickNote",
        "CriticalTailTraceFlickNote",
        "NormalTailReleaseNote",
        "CriticalTailReleaseNote",
        "NormalTickNote",
        "CriticalTickNote",
        "DamageNote",
        "AnchorNote",
        "TransientHiddenTickNote",
        "FakeNormalTapNote",
        "FakeCriticalTapNote",
        "FakeNormalFlickNote",
        "FakeCriticalFlickNote",
        "FakeNormalTraceNote",
        "FakeCriticalTraceNote",
        "FakeNormalTraceFlickNote",
        "FakeCriticalTraceFlickNote",
        "FakeNormalReleaseNote",
        "FakeCriticalReleaseNote",
        "FakeNormalHeadTapNote",
        "FakeCriticalHeadTapNote",
        "FakeNormalHeadFlickNote",
        "FakeCriticalHeadFlickNote",
        "FakeNormalHeadTraceNote",
        "FakeCriticalHeadTraceNote",
        "FakeNormalHeadTraceFlickNote",
        "FakeCriticalHeadTraceFlickNote",
        "FakeNormalHeadReleaseNote",
        "FakeCriticalHeadReleaseNote",
        "FakeNormalTailTapNote",
        "FakeCriticalTailTapNote",
        "FakeNormalTailFlickNote",
        "FakeCriticalTailFlickNote",
        "FakeNormalTailTraceNote",
        "FakeCriticalTailTraceNote",
        "FakeNormalTailTraceFlickNote",
        "FakeCriticalTailTraceFlickNote",
        "FakeNormalTailReleaseNote",
        "FakeCriticalTailReleaseNote",
        "FakeNormalTickNote",
        "FakeCriticalTickNote",
        "FakeDamageNote",
        "FakeAnchorNote",
        "FakeTransientHiddenTickNote",
    }


def detect(
    data: str | bytes | bytearray | abc.Mapping, *, skip_gzip=False, skip_json=False
) -> None | Literal["base", "chcy", "pysekai"]:
    if isinstance(data, (bytes, bytearray, memoryview)):
        if not skip_gzip:
            gz = None
            try:
                gz = gzip.GzipFile(fileobj=io.BytesIO(data), mode="rb", mtime=0)
                data = gz.read()
            except gzip.BadGzipFile:
                return
            finally:
                if gz is not None:
                    gz.close()
    if isinstance(data, (str, bytes, bytearray, memoryview)):
        if not skip_json:
            try:
                level_data = json.loads(data)
            except json.JSONDecodeError:
                return
        else:
            raise ValueError("skip_json used when data is not parsed")
    else:
        level_data = data

    try:
        if not "bgmOffset" in level_data:
            return
        archetypes = set(str(ent["archetype"]) for ent in level_data["entities"])
        base_archetypes = _base_engine_archetypes()
        chcy_archetypes = _chcy_engine_archetypes()
        pysk_archetypes = _pysekai_engine_archetypes()

        base_unique_archetypes = base_archetypes - chcy_archetypes - pysk_archetypes
        if any(archetype in base_unique_archetypes for archetype in archetypes):
            return "base"

        chcy_unique_archetypes = chcy_archetypes - base_archetypes - pysk_archetypes
        if any(archetype in chcy_unique_archetypes for archetype in archetypes):
            return "chcy"

        pysk_unique_archetypes = pysk_archetypes - base_archetypes - chcy_archetypes
        if any(archetype in pysk_unique_archetypes for archetype in archetypes):
            return "pysekai"

        shared_archetypes = base_archetypes & chcy_archetypes & pysk_archetypes
        if all(archetype not in shared_archetypes for archetype in archetypes):
            # Archetype doesn't match anything pjsk related
            return
        # Default to next-sekai
        return "pysekai"
    except:
        return
