import json
import gzip
from typing import IO, List, Union

from ...notes.score import Score
from ...notes.metadata import MetaData
from ...notes.bpm import Bpm
from ...notes.timescale import TimeScaleGroup, TimeScalePoint
from ...notes.single import Single
from ...notes.slide import Slide, SlideStartPoint, SlideRelayPoint, SlideEndPoint
from ...notes.guide import Guide, GuidePoint

from ...notes.engine.archetypes import EngineArchetypeName, EngineArchetypeDataName


def load(fp: IO) -> Score:
    """Load a pjsekai LevelData file and convert it to a Score object."""
    # check first 2 bytes of possible gzip
    start = fp.peek(2) if hasattr(fp, "peek") else fp.read(2)
    if not hasattr(fp, "peek"):
        fp.seek(0)  # set pointer back to start
    if start[:2] == b"\x1f\x8b":  # GZIP magic number
        with gzip.GzipFile(fileobj=fp, mode="rb", mtime=0) as gz:
            leveldata = json.load(gz)
    else:
        leveldata = json.load(fp)

    metadata = MetaData(
        title="",
        artist="",
        designer="",
        waveoffset=leveldata.get("bgmOffset", 0),
        requests=["ticks_per_beat 480"],
    )

    notes: List[Union[Bpm, TimeScaleGroup, Single, Slide, Guide]] = []

    directions = {
        -1: "left",
        0: "up",
        1: "right",
    }

    eases = {
        -1: "out",
        0: "linear",
        1: "in",
    }

    def reverse_single_archetype(archetype: str):
        critical = "Critical" in archetype
        trace = "Trace" in archetype
        return critical, trace

    entities_raw = leveldata.get("entities", []) or []

    ref_to_raw = {}
    for e in entities_raw:
        name = e.get("name")
        if name:
            ref_to_raw[name] = e

    def get_field_raw(entity_raw: dict, field_name: str):
        """Return either numeric value or a raw ref string for a field in an entity."""
        for d in entity_raw.get("data", []):
            if d.get("name") == field_name:
                if "value" in d:
                    return d["value"]
                if "ref" in d:
                    return d["ref"]
        return None

    slide_related_raw = []
    has_bpm = False

    for entity in entities_raw:
        archetype = entity.get("archetype")
        data = {d["name"]: d.get("value", d.get("ref")) for d in entity.get("data", [])}

        if not archetype:
            continue

        if archetype == "SimLine":
            # ignore simlines
            continue

        # BPM
        if archetype == EngineArchetypeName.BpmChange:
            notes.append(
                Bpm(
                    beat=round(data[EngineArchetypeDataName.Beat], 6),
                    bpm=data[EngineArchetypeDataName.Bpm],
                )
            )
            has_bpm = True
            continue

        # TimeScale
        if archetype == EngineArchetypeName.TimeScaleChange:
            group = TimeScaleGroup()
            group.append(
                TimeScalePoint(
                    beat=round(data[EngineArchetypeDataName.Beat], 6),
                    timeScale=data[EngineArchetypeDataName.TimeScale],
                )
            )
            notes.append(group)
            continue

        # Single / Tap / Flick / Trace Notes (non-slide)
        if "Note" in archetype and "Slide" not in archetype:
            critical, trace = reverse_single_archetype(archetype)
            notes.append(
                Single(
                    beat=round(data[EngineArchetypeDataName.Beat], 6),
                    critical=critical,
                    lane=data.get("lane", 0),
                    size=data.get("size", 1),
                    trace=trace,
                    direction=(
                        directions[data["direction"]]
                        if data.get("direction") is not None
                        else None
                    ),
                    timeScaleGroup=0,
                )
            )
            continue

        # handle slides in second pass
        if (
            "Slide" in archetype
            or "Connector" in archetype
            or archetype.endswith("TickNote")
            or "AttachedSlide" in archetype
        ):
            slide_related_raw.append(entity)
            continue

    from collections import defaultdict

    # Helper to get the data map for an entity (value or ref)
    def entity_data_map(entity_raw: dict) -> dict:
        m = {}
        for d in entity_raw.get("data", []):
            if "value" in d:
                m[d["name"]] = d["value"]
            elif "ref" in d:
                m[d["name"]] = d["ref"]
        return m

    # collect connector entities (raw) and store parsed data map alongside
    connector_raws = [
        e
        for e in slide_related_raw
        if e.get("archetype") and "Connector" in e.get("archetype")
    ]

    # store list of tuples (raw_entity, data_map) keyed by (start_ref, end_ref)
    connectors_by_slide = defaultdict(list)
    for conn in connector_raws:
        data_map = entity_data_map(conn)
        start_ref = data_map.get("start")
        end_ref = data_map.get("end")
        # only group if both refs exist
        if start_ref and end_ref:
            connectors_by_slide[(start_ref, end_ref)].append((conn, data_map))

    # helper to build a joint/point object from a raw entity
    def raw_to_point(raw):
        arch = raw.get("archetype", "")
        beat = get_field_raw(raw, EngineArchetypeDataName.Beat)
        beat = round(beat, 6) if isinstance(beat, (int, float)) else None
        lane = get_field_raw(raw, "lane")
        size = get_field_raw(raw, "size")
        # NOTE: joint-level ease is a fallback — connector entities usually carry the real ease
        ease_val = get_field_raw(raw, "ease")
        ease_name = eases.get(ease_val) if ease_val is not None else None
        critical = "Critical" in arch
        # judgeType: guess from archetype
        if "Trace" in arch:
            judgeType = "trace"
        elif "IgnoredSlideTickNote" in arch:
            judgeType = "none"
        else:
            judgeType = "normal"

        return {
            "arch": arch,
            "beat": beat,
            "lane": lane,
            "size": size,
            "ease": ease_name,
            "critical": critical,
            "judgeType": judgeType,
        }

    # Now iterate slide groups and create Slide or Guide objects
    for (start_ref, end_ref), conns in connectors_by_slide.items():
        # conns is list of (conn_raw_entity, data_map)
        first_conn_raw, first_conn_map = conns[0]
        first_conn_arch = first_conn_raw.get("archetype", "")
        active = "Active" in first_conn_arch
        slide_critical = "Critical" in first_conn_arch

        # Build map of connector metadata keyed by (head_ref, tail_ref)
        # connector_meta[(head_ref, tail_ref)] = {"ease_val": ..., "arch": ...}
        connector_meta = {}
        for conn_raw, conn_map in conns:
            head_ref = conn_map.get("head")
            tail_ref = conn_map.get("tail")
            ease_val = conn_map.get("ease")  # numeric -1/0/1 in exporter
            connector_meta[(head_ref, tail_ref)] = {
                "ease_val": ease_val,
                "arch": conn_raw.get("archetype", ""),
            }

        # Collect joint refs used by connectors (head/tail), and include start & end refs themselves
        joint_refs = []
        for conn_raw, conn_map in conns:
            head = conn_map.get("head")
            tail = conn_map.get("tail")
            if head:
                joint_refs.append(head)
            if tail:
                joint_refs.append(tail)
        # include start/end themselves (they are refs to start/end entities)
        joint_refs.append(start_ref)
        joint_refs.append(end_ref)
        # unique and preserve insertion order
        unique_joint_refs = list(dict.fromkeys(joint_refs))

        # expand to raw entities and sort by beat (some hidden ticks may only have beat)
        joint_raws = []
        for ref in unique_joint_refs:
            raw = ref_to_raw.get(ref)
            if raw:
                joint_raws.append((ref, raw_to_point(raw)))
        joint_raws.sort(key=lambda x: (x[1]["beat"] if x[1]["beat"] is not None else 0))

        # build connection objects in beat order
        connections_list = []
        n_joints = len(joint_raws)
        for idx, (ref, info) in enumerate(joint_raws):
            arch = info["arch"]

            # Determine connector-provided ease:
            # 1) try incoming connector (prev -> ref)
            # 2) else try outgoing connector (ref -> next)
            # 3) else fall back to joint ease or "linear"
            ease_name_for_this = None

            if idx > 0:
                prev_ref = joint_raws[idx - 1][0]
                incoming = connector_meta.get((prev_ref, ref))
                if incoming:
                    ease_name_for_this = eases.get(incoming.get("ease_val"))
            if ease_name_for_this is None and idx < n_joints - 1:
                next_ref = joint_raws[idx + 1][0]
                outgoing = connector_meta.get((ref, next_ref))
                if outgoing:
                    ease_name_for_this = eases.get(outgoing.get("ease_val"))

            # joint fallback (rare): use info["ease"] if present
            if ease_name_for_this is None:
                if info.get("ease") is not None:
                    ease_name_for_this = info.get("ease")
                else:
                    ease_name_for_this = "linear"  # last resort default

            # Create slide points using the resolved ease where appropriate
            if "Start" in arch or "StartNote" in arch:
                sp = SlideStartPoint(
                    type="start",
                    beat=info["beat"],
                    lane=info["lane"] if info["lane"] is not None else 0,
                    size=info["size"] if info["size"] is not None else 1,
                    ease=ease_name_for_this,
                    judgeType=info["judgeType"],
                    critical=info["critical"],
                    timeScaleGroup=0,
                )
                connections_list.append(sp)
            elif "End" in arch or "EndNote" in arch:
                raw = ref_to_raw.get(ref, {})
                dir_val = get_field_raw(raw, "direction")
                dir_name = directions.get(dir_val) if dir_val is not None else None
                ep = SlideEndPoint(
                    type="end",
                    beat=info["beat"],
                    lane=info["lane"] if info["lane"] is not None else 0,
                    size=info["size"] if info["size"] is not None else 1,
                    judgeType=info["judgeType"],
                    critical=info["critical"],
                    direction=dir_name,
                    timeScaleGroup=0,
                )
                connections_list.append(ep)
            elif "HiddenSlideTickNote" in arch or "HiddenSlide" in arch:
                pass  # these are generated on export
            elif (
                "AttachedSlide" in arch
                or "AttachedSlideTickNote" in arch
                or "Attached" in arch
            ):
                rp = SlideRelayPoint(
                    type="attach",
                    beat=info["beat"],
                    lane=None,
                    size=None,
                    ease=None,
                    timeScaleGroup=0,
                    critical=info["critical"],
                )
                connections_list.append(rp)
            elif (
                "TickNote" in arch
                or "SlideTick" in arch
                or "SlideConnector" in arch
                or "IgnoredSlideTickNote" in arch
            ):
                rp = SlideRelayPoint(
                    type="tick",
                    beat=info["beat"],
                    lane=info["lane"] if info["lane"] is not None else 0,
                    size=info["size"] if info["size"] is not None else 1,
                    ease=(
                        ease_name_for_this
                        if ease_name_for_this is not None
                        else "linear"
                    ),
                    timeScaleGroup=0,
                    critical=(
                        None if "IgnoredSlideTickNote" in arch else info["critical"]
                    ),
                )
                connections_list.append(rp)
            else:
                rp = SlideRelayPoint(
                    type="tick",
                    beat=info["beat"],
                    lane=info["lane"] if info["lane"] is not None else 0,
                    size=info["size"] if info["size"] is not None else 1,
                    ease=(
                        ease_name_for_this
                        if ease_name_for_this is not None
                        else "linear"
                    ),
                    timeScaleGroup=0,
                    critical=info["critical"],
                )
                connections_list.append(rp)

        # convert all slides without a start/end to guides
        contains_start_or_end = any(
            getattr(c, "type", None) in ("start", "end") for c in connections_list
        )
        if not active and not contains_start_or_end:
            midpoints = []
            for c in connections_list:
                if isinstance(c, SlideRelayPoint) and c.type == "tick":
                    gp = GuidePoint(
                        beat=round(c.beat, 6),
                        lane=getattr(c, "lane", 0),
                        size=getattr(c, "size", 1),
                        ease=getattr(c, "ease", "linear"),
                        timeScaleGroup=0,
                    )
                    midpoints.append(gp)
            color = "yellow" if slide_critical else "green"
            guide = Guide(midpoints=midpoints, color=color, fade="none")
            notes.append(guide)
            continue

        slide = Slide(critical=slide_critical, connections=connections_list)
        notes.append(slide)

    if not has_bpm:
        notes.insert(0, Bpm(beat=round(0, 6), bpm=160.0))

    return Score(metadata=metadata, notes=notes)
