import json
import gzip
from typing import IO, Dict, Any, List, Optional

from ...notes.score import Score
from ...notes.metadata import MetaData
from ...notes.bpm import Bpm
from ...notes.timescale import TimeScaleGroup, TimeScalePoint
from ...notes.single import Single
from ...notes.slide import Slide, SlideStartPoint, SlideRelayPoint, SlideEndPoint
from ...notes.guide import Guide, GuidePoint

from ...notes.engine.archetypes import EngineArchetypeName, EngineArchetypeDataName


# inverse maps (mirror of exporter)
_INV_DIRECTIONS = {-1: "left", 0: "up", 1: "right"}
_INV_EASES = {-2: "outin", -1: "out", 0: "linear", 1: "in", 2: "inout"}
_INV_SLIDE_STARTS = {0: "normal", 1: "trace", 2: "none"}
_INV_COLORS = {
    0: "neutral",
    1: "red",
    2: "green",
    3: "blue",
    4: "yellow",
    5: "purple",
    6: "cyan",
    7: "black",
}
_INV_FADES = {
    2: "in",
    0: "out",
    1: "none",
}


def _is_gzip_start(two_bytes: bytes) -> bool:
    return two_bytes[:2] == b"\x1f\x8b"


def _entity_data_map(entity: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for item in entity.get("data", []):
        nm = item.get("name")
        if "value" in item:
            out[nm] = item["value"]
        elif "ref" in item:
            out[nm] = item["ref"]
    return out


def _is_timescale_group_archetype(archetype: str) -> bool:
    return archetype == "TimeScaleGroup"


def _is_timescale_change_archetype(archetype: str) -> bool:
    return archetype == "TimeScaleChange"


def _is_bpm_archetype(archetype: str) -> bool:
    return archetype == EngineArchetypeName.BpmChange


def _is_simline_archetype(archetype: str) -> bool:
    return archetype == "SimLine"


def _is_slide_start_archetype(archetype: str) -> bool:
    return "SlideStartNote" in archetype


def _is_slide_end_archetype(archetype: str) -> bool:
    return "SlideEndNote" in archetype or "SlideEndFlickNote" in archetype


def _is_slide_tick_archetype(archetype: str) -> bool:
    return (
        "SlideTickNote" in archetype
        or "AttachedSlideTickNote" in archetype
        or archetype == "IgnoredSlideTickNote"
        or archetype == "HiddenSlideTickNote"
    )


def _is_slide_connector_archetype(archetype: str) -> bool:
    return archetype.endswith("SlideConnector")


def _is_single_archetype(archetype: str) -> bool:
    return any(
        x in archetype for x in ("TapNote", "FlickNote", "TraceNote", "DamageNote")
    )


def _parse_tsg_index(name: str) -> Optional[int]:
    if name.startswith("tsg:"):
        return int(name.split(":")[1])
    return None


def load(fp: IO) -> Score:
    # read JSON (possibly gzipped)
    start = fp.peek(2) if hasattr(fp, "peek") else fp.read(2)
    if not hasattr(fp, "peek"):
        fp.seek(0)
    if _is_gzip_start(start):
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

    # build entity maps
    entities_by_name: Dict[str, Dict[str, Any]] = {}
    unnamed_entities: List[Dict[str, Any]] = []
    for ent in leveldata.get("entities", []):
        name = ent.get("name")
        if name is not None:
            entities_by_name[name] = ent
        else:
            unnamed_entities.append(ent)

    parsed: Dict[str, Dict[str, Any]] = {}
    for name, ent in entities_by_name.items():
        parsed[name] = {
            "archetype": ent.get("archetype", ""),
            "data": _entity_data_map(ent),
        }

    def _get_field(e: Dict[str, Any], field: str, default=None):
        if type(e["data"]) == list:
            data = _entity_data_map(e.copy())
        else:
            data = e["data"]
        val = data.get(field, default)
        if val is None and field == "timeScaleGroup":
            return 0
        return val

    def _all_entities():
        for ent in unnamed_entities:
            yield None, ent
        for name, ent in parsed.items():
            yield name, ent

    notes: List[Any] = []

    # TimeScaleGroups
    tsg_entities = [
        (n, v)
        for n, v in parsed.items()
        if _is_timescale_group_archetype(v["archetype"])
    ]
    tsg_by_index: Dict[int, TimeScaleGroup] = {}
    for name, ent in tsg_entities:
        idx = _parse_tsg_index(name)
        if idx is None:
            continue
        length = _get_field(ent, "length", 0) or 0
        changes: List[TimeScalePoint] = []
        for i in range(int(length)):
            tsc_name = f"tsc:{idx}:{i}"
            tsc_ent = parsed.get(tsc_name)
            if tsc_ent:
                beat = _get_field(tsc_ent, EngineArchetypeDataName.Beat, 0.0)
                timeScale = _get_field(tsc_ent, "timeScale", 1.0)
                changes.append(TimeScalePoint(beat=beat, timeScale=timeScale))
        if not changes:
            tsc_ent = parsed.get("tsc:0:0")
            if tsc_ent:
                beat = _get_field(tsc_ent, EngineArchetypeDataName.Beat, 0.0)
                timeScale = _get_field(tsc_ent, "timeScale", 1.0)
                changes.append(TimeScalePoint(beat=beat, timeScale=timeScale))
        tsg_by_index[idx] = TimeScaleGroup(changes=changes)
    for idx in sorted(tsg_by_index.keys()):
        notes.append(tsg_by_index[idx])

    print("✔ Hi-Speeds / Layers")

    # BPMs
    for name, ent in _all_entities():
        arch = ent["archetype"]
        if _is_bpm_archetype(arch):
            beat_key = EngineArchetypeDataName.Beat
            bpm_key = EngineArchetypeDataName.Bpm
            beat = _get_field(ent, beat_key, 0.0)
            bpm = _get_field(ent, bpm_key, None)
            if bpm is None:
                bpm = _get_field(ent, "bpm", 160.0)
            notes.append(Bpm(beat=beat, bpm=bpm))

    print("✔ BPMs")

    # Singles
    for name, ent in _all_entities():
        arch = ent["archetype"]
        if not _is_single_archetype(arch):
            continue
        if _is_simline_archetype(arch):
            continue
        if (
            _is_slide_start_archetype(arch)
            or _is_slide_end_archetype(arch)
            or _is_slide_connector_archetype(arch)
            or _is_slide_start_archetype(arch)
        ):
            continue
        if "Slide" in arch and (
            "TickNote" in arch or "Attached" in arch or "IgnoredSlideTickNote" in arch
        ):
            continue

        beat = _get_field(
            ent,
            EngineArchetypeDataName.Beat,
            None,
        )
        lane = _get_field(ent, "lane", None)
        size = _get_field(ent, "size", None)
        timeScaleGroup = _get_field(ent, "timeScaleGroup", 0)
        if isinstance(timeScaleGroup, str) and timeScaleGroup.startswith("tsg:"):
            timeScaleGroup = int(timeScaleGroup.split(":")[1])

        if arch == "DamageNote":
            s = Single(
                beat=beat,
                lane=lane,
                size=size,
                timeScaleGroup=timeScaleGroup,
                type="damage",
            )
            notes.append(s)
            continue

        critical = "Critical" in arch
        trace = "Trace" in arch
        direction_val = _get_field(ent, "direction", None)
        direction = None
        if direction_val is not None:
            if arch == "NonDirectionalTraceFlickNote":
                # specifically set up
                direction = "up"
                print(
                    "Warning: NonDirectionalTraceFlickNote encountered, not supported. Converted to directional Up trace flick note."
                )
            else:
                direction = _INV_DIRECTIONS.get(int(direction_val), None)

        if beat is None:
            continue

        s = Single(
            beat=beat,
            lane=lane,
            size=size,
            critical=critical,
            trace=trace,
            timeScaleGroup=timeScaleGroup,
            direction=direction,
        )
        notes.append(s)

    print("✔ Singles")

    # Slides

    connectors: Dict[str, Dict[str, Any]] = {}

    for name, ent in parsed.items():
        if _is_slide_connector_archetype(ent["archetype"]):
            connectors[name] = {"archetype": ent["archetype"], "data": ent["data"]}

    unnamed_conn_count = 0
    for idx, ent in enumerate(unnamed_entities):
        if ent.get("archetype") and _is_slide_connector_archetype(ent["archetype"]):
            data_map = _entity_data_map(ent)
            gen_name = f"__unnamed_conn_{unnamed_conn_count}"
            unnamed_conn_count += 1
            connectors[gen_name] = {"archetype": ent["archetype"], "data": data_map}

    connectors_by_start: Dict[str, List[tuple]] = {}
    for cname, cent in connectors.items():
        start_ref = cent["data"].get("start")
        start_name = start_ref.get("name") if isinstance(start_ref, dict) else start_ref
        if start_name is None:
            continue
        connectors_by_start.setdefault(start_name, []).append((cname, cent))

    slide_starts = [
        (n, e) for n, e in parsed.items() if _is_slide_start_archetype(e["archetype"])
    ]

    for start_name, start_ent in slide_starts:
        conns = connectors_by_start.get(start_name, [])
        if not conns:
            continue

        def _conn_head_beat(pair):
            _, cent = pair
            head_ref = cent["data"].get("head")
            head_name = head_ref.get("name") if isinstance(head_ref, dict) else head_ref
            head_ent = parsed.get(head_name)
            if head_ent:
                return _get_field(head_ent, EngineArchetypeDataName.Beat, 0.0)
            return 0.0

        conns_sorted = sorted(conns, key=_conn_head_beat)

        ease_map: Dict[str, str] = {}
        joint_critical_map: Dict[str, Optional[bool]] = {}
        for cname, cent in conns_sorted:
            conn_data = cent["data"]
            ease_val = conn_data.get("ease", None)
            ease_str = _INV_EASES.get(ease_val, None) if ease_val is not None else None
            if ease_str is not None:
                for ref_field in ("start", "head", "tail", "end"):
                    ref = conn_data.get(ref_field)
                    ref_name = ref.get("name") if isinstance(ref, dict) else ref
                    if isinstance(ref_name, str):
                        ease_map[ref_name] = ease_str
            conn_is_critical = "Critical" in cent.get("archetype", "")
            for ref_field in ("head", "tail"):
                ref = conn_data.get(ref_field)
                ref_name = ref.get("name") if isinstance(ref, dict) else ref
                if isinstance(ref_name, str):
                    joint_critical_map[ref_name] = conn_is_critical

        end_ref_candidate = None
        for _, cent in conns_sorted:
            end_ref = cent["data"].get("end")
            end_name = end_ref.get("name") if isinstance(end_ref, dict) else end_ref
            if isinstance(end_name, str):
                end_ref_candidate = end_name
                break

        start_beat = _get_field(start_ent, EngineArchetypeDataName.Beat, 0.0)
        start_lane = _get_field(start_ent, "lane", 0.0)
        start_size = _get_field(start_ent, "size", 0.0)
        start_tsg = _get_field(start_ent, "timeScaleGroup", 0)
        if isinstance(start_tsg, str) and start_tsg.startswith("tsg:"):
            start_tsg = int(start_tsg.split(":")[1])
        if "Hidden" in start_ent["archetype"]:
            start_judge = "none"
        elif "Trace" in start_ent["archetype"]:
            start_judge = "trace"
        else:
            start_judge = "normal"

        found = None
        for cname, cent in conns_sorted:
            head_ref = cent["data"].get("head")
            head_name = head_ref.get("name") if isinstance(head_ref, dict) else head_ref
            if head_name == start_name:
                found = (cname, cent)
                break

        if not found:
            raise RuntimeError(
                f"No connector where head == start for slide start '{start_name}'"
            )

        cname, cent = found
        sv = cent["data"].get("ease", None)
        if sv is None:
            raise RuntimeError(
                f"Connector '{cname}' referencing start '{start_name}' is missing 'ease'"
            )

        if isinstance(sv, str):
            start_ease = sv
        else:
            start_ease = _INV_EASES.get(sv)
        if start_ease is None:
            raise RuntimeError(
                f"Unknown ease value '{sv}' on connector '{cname}' for start '{start_name}'"
            )

        # derive start critical from the start entity OR the authoritative connector (head==start)
        # eg. HiddenSlideStartNote doesn't have Critical
        start_critical = ("Critical" in start_ent.get("archetype", "")) or (
            "Critical" in cent.get("archetype", "")
        )

        start_point = SlideStartPoint(
            beat=start_beat,
            critical=start_critical,
            ease=start_ease,
            judgeType=start_judge,
            lane=start_lane,
            size=start_size,
            timeScaleGroup=start_tsg,
        )

        joint_names: List[str] = []
        for _, cent in conns_sorted:
            data = cent["data"]
            for ref_field in ("head", "tail"):
                ref = data.get(ref_field)
                ref_name = ref.get("name") if isinstance(ref, dict) else ref
                if isinstance(ref_name, str) and ref_name not in joint_names:
                    joint_names.append(ref_name)

        conn_names_for_slide = [cname for cname, _ in conns_sorted]

        relay_points: List[SlideRelayPoint] = []
        for ent_name, ent in parsed.items():
            arch = ent["archetype"]
            if not _is_slide_tick_archetype(arch) or arch == "IgnoredSlideTickNote":
                continue

            attach_ref = ent["data"].get("attach")
            slide_ref = ent["data"].get("slide")
            ref_names = []
            if attach_ref:
                ref_names.append(
                    attach_ref.get("name")
                    if isinstance(attach_ref, dict)
                    else attach_ref
                )
            if slide_ref:
                ref_names.append(
                    slide_ref.get("name") if isinstance(slide_ref, dict) else slide_ref
                )

            if ent_name in joint_names or any(
                rn in conn_names_for_slide for rn in ref_names if rn
            ):
                beat = _get_field(ent, EngineArchetypeDataName.Beat, 0.0)
                lane = _get_field(ent, "lane", 0.0)
                size = _get_field(ent, "size", 0.0)
                tsg = _get_field(ent, "timeScaleGroup", 0)
                if isinstance(tsg, str) and tsg.startswith("tsg:"):
                    tsg = int(tsg.split(":")[1])
                rtype = "attach" if ("Attached" in arch) else "tick"

                if "Critical" in arch:
                    rcritical = True
                elif "Normal" in arch:
                    rcritical = False
                elif "Hidden" in arch or arch == "HiddenSlideTickNote":
                    rcritical = None
                else:
                    rcritical = joint_critical_map.get(ent_name, start_point.critical)

                rp_ease = ease_map.get(ent_name, start_ease)

                rp = SlideRelayPoint(
                    beat=beat,
                    ease=rp_ease,
                    lane=lane,
                    size=size,
                    timeScaleGroup=tsg,
                    type=rtype,
                    critical=rcritical,
                )
                relay_points.append(rp)

        if not end_ref_candidate or end_ref_candidate not in parsed:
            continue

        end_ent = parsed[end_ref_candidate]
        end_beat = _get_field(end_ent, EngineArchetypeDataName.Beat, 0.0)
        end_lane = _get_field(end_ent, "lane", 0.0)
        end_size = _get_field(end_ent, "size", 0.0)
        end_tsg = _get_field(end_ent, "timeScaleGroup", 0)
        if isinstance(end_tsg, str) and end_tsg.startswith("tsg:"):
            end_tsg = int(end_tsg.split(":")[1])
        if "Hidden" in end_ent["archetype"]:
            end_judge = "none"
        elif "Trace" in end_ent["archetype"]:
            end_judge = "trace"
        else:
            end_judge = "normal"
        dir_val = _get_field(end_ent, "direction", None)
        direction = (
            _INV_DIRECTIONS.get(int(dir_val), None) if dir_val is not None else None
        )

        end_critical = "Critical" in end_ent["archetype"]

        end_point = SlideEndPoint(
            beat=end_beat,
            critical=end_critical,
            judgeType=end_judge,
            lane=end_lane,
            size=end_size,
            timeScaleGroup=end_tsg,
            direction=direction,
        )

        relay_points_sorted = sorted(
            relay_points, key=lambda r: getattr(r, "beat", 0.0)
        )
        connections_list = [start_point] + relay_points_sorted + [end_point]

        slide_critical = bool(start_point.critical)

        slide_obj = Slide(critical=slide_critical, connections=connections_list)
        notes.append(slide_obj)

    print("✔ Slides")

    # Guides
    guides: List[Guide] = []

    guide_segments_raw: List[dict] = []

    for ent in unnamed_entities:
        if ent.get("archetype") == "Guide":
            data_map = {
                d["name"]: d.get("value", d.get("ref")) for d in ent.get("data", [])
            }
            guide_segments_raw.append(data_map)

    for name, ent in parsed.items():
        if ent.get("archetype") == "Guide":
            guide_segments_raw.append(ent["data"])

    def _tsg_val(val):
        if isinstance(val, str) and val.startswith("tsg:"):
            try:
                return int(val.split(":", 1)[1])
            except Exception:
                return 0
        return val if isinstance(val, (int, float)) else 0

    def _conv_ease_str(ease_val):
        if isinstance(ease_val, str):
            return ease_val
        mapped = _INV_EASES.get(ease_val)
        if mapped is None:
            raise RuntimeError(f"Unknown/missing ease value: {ease_val}")
        return mapped

    segment_nodes: List[dict] = []
    for data_map in guide_segments_raw:
        node = {
            "start": GuidePoint(
                beat=data_map.get("startBeat"),
                lane=data_map.get("startLane"),
                size=data_map.get("startSize"),
                timeScaleGroup=_tsg_val(data_map.get("startTimeScaleGroup")),
                ease=None,
            ),
            "head": GuidePoint(
                beat=data_map.get("headBeat"),
                lane=data_map.get("headLane"),
                size=data_map.get("headSize"),
                timeScaleGroup=_tsg_val(data_map.get("headTimeScaleGroup")),
                ease=None,
            ),
            "tail": GuidePoint(
                beat=data_map.get("tailBeat"),
                lane=data_map.get("tailLane"),
                size=data_map.get("tailSize"),
                timeScaleGroup=_tsg_val(data_map.get("tailTimeScaleGroup")),
                ease=None,
            ),
            "end": GuidePoint(
                beat=data_map.get("endBeat"),
                lane=data_map.get("endLane"),
                size=data_map.get("endSize"),
                timeScaleGroup=_tsg_val(data_map.get("endTimeScaleGroup")),
                ease=None,
            ),
            "ease_val": data_map.get("ease", None),
            "color": _INV_COLORS.get(data_map.get("color")),
            "fade": _INV_FADES.get(data_map.get("fade")),
        }
        segment_nodes.append(node)

    head_to_segs: Dict[tuple, List[dict]] = {}
    tail_to_segs: Dict[tuple, List[dict]] = {}
    for seg in segment_nodes:
        head_key = (
            seg["head"].lane,
            seg["head"].size,
            seg["head"].beat,
            seg["head"].timeScaleGroup,
        )
        tail_key = (
            seg["tail"].lane,
            seg["tail"].size,
            seg["tail"].beat,
            seg["tail"].timeScaleGroup,
        )
        head_to_segs.setdefault(head_key, []).append(seg)
        tail_to_segs.setdefault(tail_key, []).append(seg)

    for seg_list in head_to_segs.values():
        seg_list.sort(
            key=lambda s: (
                getattr(s["head"], "beat", 0.0),
                getattr(s["tail"], "beat", 0.0),
            )
        )

    start_segments = [
        seg
        for seg in segment_nodes
        if (
            seg["head"].lane,
            seg["head"].size,
            seg["head"].beat,
            seg["head"].timeScaleGroup,
        )
        not in tail_to_segs
    ]

    start_segments.sort(key=lambda s: getattr(s["head"], "beat", 0.0))

    for start_seg in start_segments:
        chain: List[dict] = []
        chain.append(start_seg)
        next_key = (
            start_seg["tail"].lane,
            start_seg["tail"].size,
            start_seg["tail"].beat,
            start_seg["tail"].timeScaleGroup,
        )
        while True:
            seg_list = head_to_segs.get(next_key)
            if not seg_list:
                break
            nxt = seg_list.pop(0)
            chain.append(nxt)
            next_key = (
                nxt["tail"].lane,
                nxt["tail"].size,
                nxt["tail"].beat,
                nxt["tail"].timeScaleGroup,
            )

        # Build midpoints: start followed by each tail in chain
        midpoints: List[GuidePoint] = []
        # set start ease from first segment (required)
        first_seg = chain[0]
        sease_val = first_seg.get("ease_val", None)
        start_ease = _conv_ease_str(sease_val)
        sp = first_seg["start"]
        sp.ease = start_ease
        midpoints.append(sp)

        # For each segment in chain, set that segment's head.ease (required),
        # append its tail (tail.ease will be set when that tail becomes head of next segment).
        for seg in chain:
            # head corresponds to previous midpoint (could be same as start)
            hease_val = seg.get("ease_val", None)
            head_ease = _conv_ease_str(hease_val)
            head_gp = seg["head"]
            head_gp.ease = head_ease
            # append tail
            tail_gp = seg["tail"]
            midpoints.append(tail_gp)

        # end point: allowed to default to "linear"
        end_point = chain[-1]["end"]
        end_point.ease = "linear"
        midpoints.append(end_point)

        guides.append(
            Guide(midpoints=midpoints, color=start_seg["color"], fade=start_seg["fade"])
        )

    notes.extend(guides)

    print("✔ Guides")

    # assemble score
    score = Score(metadata=metadata, notes=notes)
    return score
