import json
import gzip
from typing import IO, Any, Dict, List, Tuple, Optional
from collections import defaultdict

from ...notes.score import Score
from ...notes.metadata import MetaData
from ...notes.bpm import Bpm
from ...notes.timescale import TimeScaleGroup, TimeScalePoint
from ...notes.single import Single
from ...notes.slide import Slide, SlideStartPoint, SlideRelayPoint, SlideEndPoint
from ...notes.guide import Guide, GuidePoint

from ...notes.engine.archetypes import EngineArchetypeName, EngineArchetypeDataName


_PJ_EASES_INV = {-1: "out", 0: "linear", 1: "in"}


def _is_gzip_start(two_bytes: bytes) -> bool:
    return two_bytes[:2] == b"\x1f\x8b"


def load(fp: IO) -> Score:
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

    entities_raw: List[Dict[str, Any]] = leveldata.get("entities", []) or []

    ref_to_raw: Dict[str, Dict[str, Any]] = {}
    for ent in entities_raw:
        name = ent.get("name")
        if name:
            ref_to_raw[name] = ent

    def get_field_raw(entity_raw: Dict[str, Any], field_name: str):
        for d in entity_raw.get("data", []):
            if d.get("name") == field_name:
                if "value" in d:
                    return d["value"]
                if "ref" in d:
                    return d["ref"]
        return None

    def entity_data_map(entity_raw: Dict[str, Any]) -> Dict[str, Any]:
        m: Dict[str, Any] = {}
        for d in entity_raw.get("data", []):
            if "value" in d:
                m[d["name"]] = d["value"]
            elif "ref" in d:
                m[d["name"]] = d["ref"]
        return m

    notes: List[Any] = []
    has_bpm = False

    beat_key = (
        EngineArchetypeDataName.Beat
        if hasattr(EngineArchetypeDataName, "Beat")
        else "beat"
    )
    bpm_key = (
        EngineArchetypeDataName.Bpm
        if hasattr(EngineArchetypeDataName, "Bpm")
        else "bpm"
    )

    directions = {-1: "left", 0: "up", 1: "right"}

    slide_related_raw: List[Dict[str, Any]] = []

    for ent in entities_raw:
        arch = ent.get("archetype")
        if not arch:
            continue
        if arch == "SimLine":
            continue
        if arch == EngineArchetypeName.BpmChange:
            d = entity_data_map(ent)
            beat = d.get(beat_key, d.get("beat", 0.0))
            bpm = d.get(bpm_key, d.get("bpm", 160.0))
            notes.append(Bpm(beat=round(beat, 6), bpm=bpm))
            has_bpm = True
            continue
        if arch == EngineArchetypeName.TimeScaleChange:
            d = entity_data_map(ent)
            beat = d.get(beat_key, d.get("beat", 0.0))
            ts = d.get(EngineArchetypeDataName.TimeScale, d.get("timeScale", 1.0))
            notes.append(
                TimeScaleGroup(changes=[TimeScalePoint(beat=beat, timeScale=ts)])
            )
            continue
        if "Note" in arch and "Slide" not in arch:
            d = entity_data_map(ent)
            beat = d.get(beat_key, d.get("beat", None))
            if beat is None:
                continue
            critical = "Critical" in arch
            trace = "Trace" in arch
            lane = d.get("lane", 0)
            size = d.get("size", 1)
            dir_val = d.get("direction", None)
            direction = directions.get(dir_val) if dir_val is not None else None
            notes.append(
                Single(
                    beat=round(beat, 6),
                    lane=lane,
                    size=size,
                    critical=critical,
                    trace=trace,
                    timeScaleGroup=0,
                    direction=direction,
                )
            )
            continue
        if (
            "Slide" in arch
            or "Connector" in arch
            or arch.endswith("TickNote")
            or "AttachedSlide" in arch
        ):
            slide_related_raw.append(ent)
            continue

    if not has_bpm:
        notes.insert(0, Bpm(beat=round(0.0, 6), bpm=160.0))

    connector_raws = [
        e
        for e in slide_related_raw
        if e.get("archetype") and "Connector" in e.get("archetype")
    ]
    connectors_by_slide: Dict[
        Tuple[str, str], List[Tuple[Dict[str, Any], Dict[str, Any]]]
    ] = defaultdict(list)
    for conn in connector_raws:
        cmap = entity_data_map(conn)
        # assume start/end are stored as simple strings (no dict fallback)
        start_ref = cmap.get("start")
        end_ref = cmap.get("end")
        if not start_ref or not end_ref:
            continue
        connectors_by_slide[(start_ref, end_ref)].append((conn, cmap))

    def raw_to_joint_info(raw: Dict[str, Any]) -> Dict[str, Any]:
        arch = raw.get("archetype", "")
        d = entity_data_map(raw)
        beat = d.get(beat_key, d.get("beat", None))
        if isinstance(beat, (int, float)):
            beat = round(beat, 6)
        lane = d.get("lane")
        size = d.get("size")
        ease_val = d.get("ease", None)
        ease_joint = None
        if ease_val is not None:
            if isinstance(ease_val, str):
                ease_joint = ease_val
            else:
                ease_joint = _PJ_EASES_INV.get(ease_val)
        critical = "Critical" in arch
        judgeType = (
            "trace"
            if "Trace" in arch
            else ("none" if "IgnoredSlideTickNote" in arch else "normal")
        )
        return {
            "arch": arch,
            "beat": beat,
            "lane": lane,
            "size": size,
            "ease_joint": ease_joint,
            "critical": critical,
            "judgeType": judgeType,
        }

    results_slides: List[Slide] = []
    results_guides: List[Guide] = []

    for (start_ref, end_ref), conns in connectors_by_slide.items():
        connector_meta: Dict[Tuple[str, str], Dict[str, Any]] = {}
        connector_order: List[Tuple[str, str]] = []
        for c_raw, c_map in conns:
            head_ref = c_map.get("head")
            tail_ref = c_map.get("tail")
            if head_ref is None or tail_ref is None:
                continue
            connector_meta[(head_ref, tail_ref)] = {
                "ease_val": c_map.get("ease", None),
                "archetype": c_raw.get("archetype", ""),
            }
            connector_order.append((head_ref, tail_ref))

        head_to_tails: Dict[str, List[str]] = defaultdict(list)
        for h, t in connector_order:
            head_to_tails[h].append(t)

        chain_refs: List[str] = []
        cur = start_ref
        chain_refs.append(cur)
        visited = {cur}
        loop_guard = 0
        while True:
            loop_guard += 1
            if loop_guard > 5000:
                raise RuntimeError(
                    f"Infinite loop reconstructing connectors for slide {start_ref}->{end_ref}"
                )
            if cur == end_ref:
                break
            tails = head_to_tails.get(cur, [])
            if not tails:
                break
            next_ref = None
            for t in tails:
                if t not in visited:
                    next_ref = t
                    break
            if next_ref is None:
                next_ref = tails[0]
            if next_ref in visited:
                chain_refs.append(next_ref)
                break
            chain_refs.append(next_ref)
            visited.add(next_ref)
            cur = next_ref

        if chain_refs[-1] != end_ref:
            continue

        joint_info_list: List[Tuple[str, Dict[str, Any]]] = []
        missing_raw = False
        for r in chain_refs:
            raw = ref_to_raw.get(r)
            if raw is None:
                missing_raw = True
                break
            joint_info_list.append((r, raw_to_joint_info(raw)))
        if missing_raw or len(joint_info_list) < 2:
            continue

        n = len(joint_info_list)
        connections_list: List[Any] = []

        def get_authoritative_connector_for(head_ref: str, tail_ref: Optional[str]):
            if tail_ref is not None and (head_ref, tail_ref) in connector_meta:
                return connector_meta[(head_ref, tail_ref)]
            for h, t in connector_order:
                if h == head_ref:
                    return connector_meta.get((h, t))
            return None

        first_conn_arch = conns[0][0].get("archetype", "") if conns else ""
        slide_is_critical_from_connector = "Critical" in first_conn_arch

        for idx, (ref, info) in enumerate(joint_info_list):
            is_first = idx == 0
            is_last = idx == n - 1

            beat = info.get("beat")
            if (is_first or is_last) and beat is None:
                which = "start" if is_first else "end"
                raise RuntimeError(
                    f"{which.capitalize()} point for slide ({start_ref}->{end_ref}) missing beat."
                )
            if is_first and info.get("lane") is None:
                raise RuntimeError(
                    f"Start point for slide ({start_ref}->{end_ref}) missing lane."
                )
            if is_first and info.get("size") is None:
                raise RuntimeError(
                    f"Start point for slide ({start_ref}->{end_ref}) missing size."
                )
            if is_last and info.get("lane") is None:
                raise RuntimeError(
                    f"End point for slide ({start_ref}->{end_ref}) missing lane."
                )
            if is_last and info.get("size") is None:
                raise RuntimeError(
                    f"End point for slide ({start_ref}->{end_ref}) missing size."
                )

            if is_last:
                ease_name = "linear"
            else:
                next_ref = joint_info_list[idx + 1][0]
                meta = get_authoritative_connector_for(ref, next_ref)
                ease_name = None
                if meta is not None:
                    ev = meta.get("ease_val")
                    if isinstance(ev, str):
                        ease_name = ev
                    else:
                        ease_name = _PJ_EASES_INV.get(ev)
                if ease_name is None:
                    ease_name = info.get("ease_joint")
                if ease_name is None:
                    raise RuntimeError(
                        f"Missing ease for joint '{ref}' (slide {start_ref}->{end_ref})."
                    )

            lane = info.get("lane")
            size = info.get("size")
            if lane is None or size is None:
                prev_lane = None
                prev_size = None
                for j in range(idx - 1, -1, -1):
                    pl = joint_info_list[j][1].get("lane")
                    ps = joint_info_list[j][1].get("size")
                    if prev_lane is None and pl is not None:
                        prev_lane = pl
                    if prev_size is None and ps is not None:
                        prev_size = ps
                    if prev_lane is not None and prev_size is not None:
                        break
                if prev_lane is None:
                    prev_lane = joint_info_list[0][1].get("lane")
                if prev_size is None:
                    prev_size = joint_info_list[0][1].get("size")
                lane = lane if lane is not None else prev_lane
                size = size if size is not None else prev_size

            if is_first and info.get("judgeType") != "none":
                auth_meta = get_authoritative_connector_for(
                    ref, joint_info_list[idx + 1][0]
                )
                if auth_meta is None:
                    raise RuntimeError(
                        f"No connector with head == start for slide start '{ref}' (slide {start_ref}->{end_ref})."
                    )
                start_raw = ref_to_raw.get(ref, {})
                start_arch = start_raw.get("archetype", "") if start_raw else ""
                conn_arch = auth_meta.get("archetype", "") if auth_meta else ""
                start_critical = ("Critical" in start_arch) or ("Critical" in conn_arch)
                judgeType = info.get("judgeType")
                sp = SlideStartPoint(
                    beat=round(beat, 6),
                    critical=start_critical,
                    ease=ease_name,
                    judgeType=judgeType,
                    lane=lane,
                    size=size,
                    timeScaleGroup=0,
                )
                connections_list.append(sp)
                continue

            if is_last and info.get("judgeType") != "none":
                raw = ref_to_raw.get(ref, {})
                dir_val = get_field_raw(raw, "direction")
                direction = directions.get(dir_val) if dir_val is not None else None
                end_critical = "Critical" in info.get("arch", "")
                ep = SlideEndPoint(
                    beat=round(beat, 6),
                    critical=end_critical,
                    judgeType=info.get("judgeType"),
                    lane=lane,
                    size=size,
                    timeScaleGroup=0,
                    direction=direction,
                )
                connections_list.append(ep)
                continue

            arch = info.get("arch", "")

            if "HiddenSlideTickNote" in arch or "HiddenSlide" in arch:
                # per this exporter Hidden = skip
                continue

            if "IgnoredSlideTickNote" in arch:
                rp = SlideRelayPoint(
                    beat=round(beat, 6) if beat is not None else 0.0,
                    ease=ease_name,
                    lane=lane,
                    size=size,
                    timeScaleGroup=0,
                    type="tick",
                    critical=None,
                )
                connections_list.append(rp)
                continue

            if (
                "AttachedSlide" in arch
                or "AttachedSlideTickNote" in arch
                or "Attached" in arch
            ):
                rp = SlideRelayPoint(
                    beat=round(beat, 6) if beat is not None else 0.0,
                    ease=ease_name,
                    lane=lane,
                    size=size,
                    timeScaleGroup=0,
                    type="attach",
                    critical=info.get("critical"),
                )
                connections_list.append(rp)
                continue

            if "TickNote" in arch or "SlideTick" in arch or "Tick" in arch:
                rp = SlideRelayPoint(
                    beat=round(beat, 6) if beat is not None else 0.0,
                    ease=ease_name,
                    lane=lane,
                    size=size,
                    timeScaleGroup=0,
                    type="tick",
                    critical=info.get("critical"),
                )
                connections_list.append(rp)
                continue

            rp = SlideRelayPoint(
                beat=round(beat, 6) if beat is not None else 0.0,
                ease=ease_name,
                lane=lane,
                size=size,
                timeScaleGroup=0,
                type="tick",
                critical=info.get("critical"),
            )
            connections_list.append(rp)

        contains_start_or_end = any(
            getattr(c, "type", None) in ("start", "end") for c in connections_list
        )

        if not contains_start_or_end and ("Active" not in first_conn_arch):
            midpoints: List[GuidePoint] = []
            for c in connections_list:
                if isinstance(c, SlideRelayPoint) and c.type == "tick":
                    gp = GuidePoint(
                        beat=round(c.beat, 6),
                        lane=getattr(c, "lane", 0),
                        size=getattr(c, "size", 1),
                        timeScaleGroup=0,
                        ease=getattr(c, "ease", "linear"),
                    )
                    midpoints.append(gp)
            if midpoints:
                midpoints[-1].ease = "linear"
                color = "yellow" if slide_is_critical_from_connector else "green"
                results_guides.append(
                    Guide(midpoints=midpoints, color=color, fade="none")
                )
            continue

        if not connections_list:
            continue
        start_pts = [c for c in connections_list if getattr(c, "type", None) == "start"]
        if not start_pts:
            continue
        start_point = start_pts[0]
        slide_critical = bool(getattr(start_point, "critical", False))
        slide_obj = Slide(critical=slide_critical, connections=connections_list)
        slide_obj.sort()
        results_slides.append(slide_obj)

    notes.extend(results_slides)
    notes.extend(results_guides)

    score = Score(metadata=metadata, notes=notes)
    score.sort_by_beat()
    return score
