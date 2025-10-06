from dataclasses import dataclass, asdict
from .metadata import MetaData, validate_metadata_dict_values
from .bpm import Bpm, validate_bpm_dict_values
from .timescale import TimeScaleGroup, validate_timescale_dict_values
from .single import Single, validate_single_dict_values
from .slide import (
    Slide,
    SlideStartPoint,
    SlideRelayPoint,
    SlideEndPoint,
    validate_slide_dict_values,
)
from .guide import Guide, GuidePoint, validate_guide_dict_values


# 1tickをbeatに変換
BEAT_PER_TICK = round(4 / 1920, 6)

# ノーツリストを何小節区切りにするか
# ※ノーツリスト = 重なりを調べるときに使用するリスト
BAR_INTERVAL = 0.5

# uscのレーン表記(中央が0.0)
# ↓
# 左端を1に変換するオフセット
LANE_OFFSET = 7


# ノーツの範囲を計算する
# [ 1 2 3 4 5 6 7 8 9 10 11 12 ] で占有レーンを表記する
def _calc_note_range(lane: float, size: float) -> list[int]:
    note_leftpos = int(lane - size + LANE_OFFSET)
    note_size = int(size * 2)
    return [_ for _ in range(note_leftpos, note_leftpos + note_size)]


# ノーツを入れるリストの番号をbeatの値から計算する
def _calc_notelist_index(
    note: Single | SlideStartPoint | SlideRelayPoint | SlideEndPoint | GuidePoint,
) -> int:
    return int(note.beat // BAR_INTERVAL)


# BAR_INTERVALごとに区切ってノーツを入れたリストから、指定beatのリストと前後のリストにあるノーツを返す
def _get_target_notelist(
    split_tmp_notes: list[
        list[Single | SlideStartPoint | SlideRelayPoint | SlideEndPoint | GuidePoint]
    ],
    target_note: (
        Single | SlideStartPoint | SlideRelayPoint | SlideEndPoint | GuidePoint
    ),
) -> list[Single | SlideStartPoint | SlideRelayPoint | SlideEndPoint | GuidePoint]:
    index = _calc_notelist_index(target_note)
    start = max(0, index - 1)
    end = min(len(split_tmp_notes), index + 2)
    return sum(split_tmp_notes[start:end], [])


# スライド、ガイドのpointを入れたリストを返す
def _convert_tmp_notes(
    tmp_notes: list[Single | Slide | Guide],
) -> list[Single | SlideStartPoint | SlideRelayPoint | SlideEndPoint | GuidePoint]:
    tmp = []
    for note in tmp_notes:
        if isinstance(note, Slide):
            for i in note.connections:
                tmp.append(i)
        elif isinstance(note, Guide):
            for i in note.midpoints:
                tmp.append(i)
        else:
            tmp.append(note)
    return tmp


# ノーツの一部または全てが重なっているか調べる
def _get_overlap_note(
    target_note: (
        Single | SlideStartPoint | SlideRelayPoint | SlideEndPoint | GuidePoint
    ),
    split_tmp_notes: list[
        list[Single | SlideStartPoint | SlideRelayPoint | SlideEndPoint | GuidePoint]
    ],
) -> Single | SlideStartPoint | SlideRelayPoint | SlideEndPoint | GuidePoint | None:

    t_note_range = set(_calc_note_range(target_note.lane, target_note.size))
    t_note_beat = target_note.beat

    for note in _get_target_notelist(split_tmp_notes, target_note):
        # 同じインスタンス（ノーツ）の場合は飛ばす
        if target_note is note:
            continue
        # 同じ拍、かつノーツの一部または全てが重なっているか判定
        note_range = _calc_note_range(note.lane, note.size)
        if t_note_beat == note.beat and bool(t_note_range.intersection(note_range)):
            return note

    return None


# スライドが脱法（終点より後に中継点があるetc...）していないか調べ、修正する
def _check_slide(
    note: Slide,
    split_tmp_notes: list[
        list[Single | SlideStartPoint | SlideRelayPoint | SlideEndPoint | GuidePoint]
    ],
):
    for point in note.connections:
        if isinstance(point, SlideStartPoint):
            start_point = point
        elif isinstance(point, SlideEndPoint):
            end_point = point

    for point in note.connections:

        if not isinstance(point, SlideEndPoint):
            while point.beat >= end_point.beat:
                point.beat -= BEAT_PER_TICK
                while _get_overlap_note(point, split_tmp_notes) != None:
                    point.beat -= BEAT_PER_TICK

        if not isinstance(point, SlideStartPoint):
            while point.beat <= start_point.beat:
                point.beat += BEAT_PER_TICK
                while _get_overlap_note(point, split_tmp_notes) != None:
                    point.beat += BEAT_PER_TICK

        if point.beat > end_point.beat:
            point.beat, end_point.beat = end_point.beat, point.beat


def _shift_slide(note: Slide, split_tmp_notes: list[Single | Slide | Guide]):
    for point in note.connections:
        while (overlap_note := _get_overlap_note(point, split_tmp_notes)) != None:
            match point, overlap_note:

                # スライド始点 + single
                case SlideStartPoint(), Single():
                    if point.judgeType != "none" and overlap_note.trace:
                        overlap_note.beat += BEAT_PER_TICK
                    else:
                        point.beat += BEAT_PER_TICK

                # スライド始点 + スライド始点
                case SlideStartPoint(), SlideStartPoint():
                    if point.judgeType != "none" and overlap_note.judgeType == "none":
                        overlap_note.beat += BEAT_PER_TICK
                    else:
                        point.beat += BEAT_PER_TICK

                # スライド始点 + スライド中継点
                case SlideStartPoint(), SlideRelayPoint():
                    overlap_note.beat += BEAT_PER_TICK

                # スライド始点 + スライド終点
                case SlideStartPoint(), SlideEndPoint():
                    point.beat += BEAT_PER_TICK

                # スライド中継点 + ノーツ
                case SlideRelayPoint(), _:
                    point.beat += BEAT_PER_TICK

                # スライド終点 + single
                case SlideEndPoint(), Single():
                    point.beat -= BEAT_PER_TICK

                # スライド終点 + スライド始点
                case SlideEndPoint(), SlideStartPoint():
                    overlap_note.beat += BEAT_PER_TICK

                # スライド終点 + スライド中継点
                case SlideEndPoint(), SlideRelayPoint():
                    overlap_note.beat += BEAT_PER_TICK

                # スライド終点 + スライド終点
                case SlideEndPoint(), SlideEndPoint():
                    if point.judgeType == "none" or overlap_note.direction != None:
                        point.beat -= BEAT_PER_TICK
                    elif overlap_note.judgeType == "none" or point.direction != None:
                        overlap_note.beat -= BEAT_PER_TICK
                    else:
                        point.beat -= BEAT_PER_TICK

                case SlideEndPoint(), _:
                    point.beat -= BEAT_PER_TICK

                case _, _:
                    point.beat += BEAT_PER_TICK

    _check_slide(note, split_tmp_notes)


def _shift_guide(note: Guide, split_tmp_notes: list[Single | Slide | Guide]):
    for point in note.midpoints:
        while _get_overlap_note(point, split_tmp_notes) != None:
            point.beat += BEAT_PER_TICK

    note.midpoints.sort(key=lambda x: x.beat)


def _shift_single(note: Single, split_tmp_notes: list[Single | Slide | Guide]):
    while (overlap_note := _get_overlap_note(note, split_tmp_notes)) != None:
        match note, overlap_note:
            case _, Single(trace=True):
                overlap_note.beat += BEAT_PER_TICK
            case _, SlideStartPoint():
                overlap_note.beat += BEAT_PER_TICK
            case _, SlideRelayPoint():
                overlap_note.beat += BEAT_PER_TICK
            case _, SlideEndPoint():
                overlap_note.beat -= BEAT_PER_TICK
            case _, GuidePoint():
                overlap_note.beat += BEAT_PER_TICK
            case _, _:
                note.beat += BEAT_PER_TICK


def usc_remove_fake_field(notes: list) -> list:
    for note in notes:
        note.pop("fake", 0)
        if "connectors" in note:
            for c in note["connectors"]:
                c.pop("fake", 0)
        if "midpoints" in note:
            for m in note["midpoints"]:
                m.pop("fake", 0)


class InvalidNoteError(Exception):
    def __init__(self, note: dict, t: str, error_message: str):
        self.note = note
        self.error_message = error_message
        super().__init__(f"Invalid {t} note: {self.note}. Error: {self.error_message}")


@dataclass
class Score:
    metadata: MetaData
    notes: list[Bpm | TimeScaleGroup | Single | Slide | Guide]

    def compare(self, score: "Score") -> None:
        from collections import defaultdict
        import pprint

        self.sort_by_beat()
        score.sort_by_beat()

        def normalize_single(s: Single):
            return {
                "type": "single" if getattr(s, "type", "tap") != "damage" else "damage",
                "beat": s.beat,
                "lane": s.lane,
                "size": s.size,
                "critical": bool(getattr(s, "critical", False)),
                "trace": bool(getattr(s, "trace", False)),
                "direction": getattr(s, "direction", None),
                "timeScaleGroup": getattr(s, "timeScaleGroup", 0),
            }

        def normalize_bpm(b: Bpm):
            return {"type": "bpm", "beat": b.beat, "bpm": b.bpm}

        def normalize_tsg(tsg: TimeScaleGroup):
            # sort changes by beat
            changes = sorted(
                getattr(tsg, "changes", []), key=lambda c: getattr(c, "beat", 0.0)
            )
            return {"type": "tsg", "changes": [(c.beat, c.timeScale) for c in changes]}

        def normalize_slide(sl: Slide):
            conns = list(getattr(sl, "connections", []))
            # sort by beat
            conns_sorted = sorted(conns, key=lambda c: getattr(c, "beat", 0.0))
            # create list of normalized connection dicts
            norm_conns = []
            for c in conns_sorted:
                common = {
                    "type": getattr(c, "type", None),
                    "beat": getattr(c, "beat", None),
                    "lane": getattr(c, "lane", None),
                    "size": getattr(c, "size", None),
                    "timeScaleGroup": getattr(c, "timeScaleGroup", 0),
                }
                # optional fields
                if hasattr(c, "critical"):
                    common["critical"] = getattr(c, "critical")
                if hasattr(c, "ease"):
                    common["ease"] = getattr(c, "ease")
                if hasattr(c, "judgeType"):
                    common["judgeType"] = getattr(c, "judgeType")
                if hasattr(c, "direction"):
                    common["direction"] = getattr(c, "direction")
                norm_conns.append(common)
            # start and end beats for key
            start_beat = next(
                (c["beat"] for c in norm_conns if c["type"] == "start"), None
            )
            end_beat = next(
                (c["beat"] for c in reversed(norm_conns) if c["type"] == "end"), None
            )
            return {
                "type": "slide",
                "critical": bool(getattr(sl, "critical", False)),
                "start_beat": start_beat,
                "end_beat": end_beat,
                "connections": norm_conns,
            }

        def normalize_guide(g: Guide):
            mids = list(getattr(g, "midpoints", []))
            mids_sorted = sorted(mids, key=lambda m: getattr(m, "beat", 0.0))
            norm = []
            for m in mids_sorted:
                norm.append(
                    {
                        "beat": getattr(m, "beat", None),
                        "lane": getattr(m, "lane", None),
                        "size": getattr(m, "size", None),
                        "timeScaleGroup": getattr(m, "timeScaleGroup", 0),
                        "ease": getattr(m, "ease", None),
                    }
                )
            # start & end keys
            start_beat = norm[0]["beat"] if norm else None
            end_beat = norm[-1]["beat"] if norm else None
            return {
                "type": "guide",
                "start_beat": start_beat,
                "end_beat": end_beat,
                "midpoints": norm,
                "color": getattr(g, "color", None),
                "fade": getattr(g, "fade", None),
            }

        # build lists of normalized notes for both scores
        def build_normalized_list(notes_list):
            norm_list = []
            for n in notes_list:
                if isinstance(n, Bpm):
                    continue
                    norm_list.append((normalize_bpm(n), n))
                elif isinstance(n, TimeScaleGroup):
                    continue
                    norm_list.append((normalize_tsg(n), n))
                elif isinstance(n, Single):
                    norm_list.append((normalize_single(n), n))
                elif isinstance(n, Slide):
                    norm_list.append((normalize_slide(n), n))
                elif isinstance(n, Guide):
                    norm_list.append((normalize_guide(n), n))
                else:
                    # fallback: use repr
                    norm_list.append(({"type": type(n).__name__, "repr": repr(n)}, n))
            return norm_list

        ours = build_normalized_list(self.notes)
        theirs = build_normalized_list(score.notes)

        # index their notes by "primary key" for candidate matching
        def primary_key(norm):
            t = norm.get("type")
            if t == "single" or t == "damage":
                return ("single", norm.get("beat"), norm.get("lane"), norm.get("size"))
            if t == "bpm":
                return ("bpm", norm.get("beat"))
            if t == "tsg":
                changes = norm.get("changes", [])
                if changes:
                    return ("tsg", changes[0][0], changes[-1][0], len(changes))
                return ("tsg", 0.0, 0.0, 0)
            if t == "slide":
                return ("slide", norm.get("start_beat"), norm.get("end_beat"))
            if t == "guide":
                return (
                    "guide",
                    norm.get("start_beat"),
                    norm.get("end_beat"),
                    norm.get("color"),
                )
            return (t,)

        their_index = defaultdict(list)
        for idx, (n, orig) in enumerate(theirs):
            their_index[primary_key(n)].append((idx, n, orig))

        used_their = set()
        extra = []
        different = []
        slide_relay_diffs = []
        pp = pprint.PrettyPrinter(width=120)

        # try to match each of our notes
        for idx_o, (on, oorig) in enumerate(ours):
            pk = primary_key(on)
            candidates = their_index.get(pk, [])
            matched_exact = None
            matched_idx = None
            # try to find exact equal candidate
            for tidx, tn, torig in candidates:
                if tidx in used_their:
                    continue
                # exact equality of normalized dicts (except for slides: we'll treat relays separately)
                if on == tn:
                    matched_exact = (tidx, tn, torig)
                    matched_idx = tidx
                    break
            if matched_exact:
                used_their.add(matched_idx)
                continue

            # no exact match -> try to find candidate with same primary key (for "different")
            candidate = None
            for tidx, tn, torig in candidates:
                if tidx in used_their:
                    continue
                candidate = (tidx, tn, torig)
                break

            if candidate is None:
                # nothing matched: this note is extra in self
                extra.append(on)
                continue

            tidx, tn, torig = candidate
            used_their.add(tidx)

            # now determine if it is "different" or "slide relay-only difference"
            if on.get("type") == "slide" and tn.get("type") == "slide":
                # compare connections but focus on relay (tick/attach) differences
                # extract relays (type != start and != end)
                def extract_relays(conns):
                    return [c for c in conns if c.get("type") not in ("start", "end")]

                our_relays = extract_relays(on.get("connections", []))
                their_relays = extract_relays(tn.get("connections", []))

                # canonicalize relay tuples for set-diff: (beat,lane,size,type,critical)
                def relay_key(r):
                    return (
                        r.get("beat"),
                        r.get("lane"),
                        r.get("size"),
                        r.get("type"),
                        r.get("critical"),
                    )

                our_set = set(relay_key(r) for r in our_relays)
                their_set = set(relay_key(r) for r in their_relays)

                extra_relays = sorted(
                    [r for r in our_relays if relay_key(r) not in their_set],
                    key=lambda x: (x.get("beat", 0.0), x.get("lane")),
                )
                missing_relays = sorted(
                    [r for r in their_relays if relay_key(r) not in our_set],
                    key=lambda x: (x.get("beat", 0.0), x.get("lane")),
                )

                # if only relay differences exist, record them specially (don't mark whole slide "different")
                if extra_relays or missing_relays:
                    slide_relay_diffs.append(
                        {
                            "our_slide_key": pk,
                            "extra_relays": extra_relays,
                            "missing_relays": missing_relays,
                            "our_slide": on,
                            "their_slide": tn,
                        }
                    )
                    # still continue: do not mark as "different" overall for relay-only diffs
                    continue

                # if relay sets same but connections differ elsewhere, treat as different
                if on != tn:
                    different.append({"ours": on, "theirs": tn})
                else:
                    # identical (shouldn't reach here because we checked exact equality earlier)
                    pass

            else:
                # For non-slide types: if normalized dicts differ -> "different"
                # but only if beat/lane/size matched (primary key). We already ensured primary key matched.
                # We will allow up to one-field diffs but report full diffs.
                if on != tn:
                    different.append({"ours": on, "theirs": tn})

        # anything in their_index not used -> missing in self
        for idx_t, (tn, torig) in enumerate(theirs):
            if idx_t not in used_their:
                # mark as missing
                missing_pk = primary_key(tn)
                (
                    missing.append(tn)
                    if "missing" in locals()
                    else locals().update(missing=[tn])
                )
        # ensure missing variable exists even if empty
        missing = globals().get("missing", [])
        extra = extra
        different = different
        slide_relay_diffs = slide_relay_diffs

        # Print summary
        def _short(n):
            t = n.get("type")
            if t == "single" or t == "damage":
                return f"Single beat={n.get('beat')} lane={n.get('lane')} size={n.get('size')} dir={n.get('direction')}"
            if t == "bpm":
                return f"BPM beat={n.get('beat')} bpm={n.get('bpm')}"
            if t == "tsg":
                ch = n.get("changes", [])
                return f"TSG changes={len(ch)} first={ch[0] if ch else None}"
            if t == "slide":
                return f"Slide start={n.get('start_beat')} end={n.get('end_beat')}"
            if t == "guide":
                return f"Guide start={n.get('start_beat')} end={n.get('end_beat')} color={n.get('color')}"
            return str(n)

        print("=== Score Comparison ===")
        print(f"Extra notes in self ({len(extra)}):")
        for e in extra:
            print(" -", _short(e))
        print()

        print(f"Missing notes (present in other but not in self) ({len(missing)}):")
        for m in missing:
            print(" -", _short(m))
        print()

        print(
            f"Different notes (same primary key but differing fields) ({len(different)}):"
        )
        for d in different:
            print(" - OURS:", _short(d["ours"]))
            print("   THEIRS:", _short(d["theirs"]))
            print("   DIFF:")
            pp.pprint({"ours": d["ours"], "theirs": d["theirs"]})
            print()

        print(
            f"Slide relay differences (extra / missing relays) ({len(slide_relay_diffs)}):"
        )
        for sd in slide_relay_diffs:
            print(" - Slide:", sd["our_slide_key"])
            if sd["extra_relays"]:
                print("   Extra relays in self:")
                pp.pprint(sd["extra_relays"])
            if sd["missing_relays"]:
                print("   Missing relays (present in other but not in self):")
                pp.pprint(sd["missing_relays"])
            print()

    def validate(self) -> bool:
        metadata_validation = validate_metadata_dict_values(self.metadata.__dict__)
        if metadata_validation:
            note_dict, error_message = metadata_validation
            raise InvalidNoteError(note_dict, "MetaData", error_message)

        for note in self.notes:
            note_dict = asdict(note)
            if isinstance(note, Bpm):
                validation_result = validate_bpm_dict_values(note_dict)
                if validation_result:
                    note_dict, error_message = validation_result
                    raise InvalidNoteError(note_dict, "BPM", error_message)
            elif isinstance(note, TimeScaleGroup):
                validation_result = validate_timescale_dict_values(note_dict)
                if validation_result:
                    note_dict, error_message = validation_result
                    raise InvalidNoteError(note_dict, "TimeScaleGroup", error_message)
            elif isinstance(note, Single):
                validation_result = validate_single_dict_values(note_dict)
                if validation_result:
                    note_dict, error_message = validation_result
                    raise InvalidNoteError(note_dict, "Single", error_message)
            elif isinstance(note, Slide):
                validation_result = validate_slide_dict_values(note_dict)
                if validation_result:
                    note_dict, error_message = validation_result
                    raise InvalidNoteError(note_dict, "Slide", error_message)
            elif isinstance(note, Guide):
                validation_result = validate_guide_dict_values(note_dict)
                if validation_result:
                    note_dict, error_message = validation_result
                    raise InvalidNoteError(note_dict, "Guide", error_message)
            else:
                raise InvalidNoteError(
                    note_dict, "UNKNOWN NOTE TYPE", "Invalid note type in list."
                )
        return True

    def delete_fake_notes(self):
        notes = []
        for note in self.notes:
            if hasattr(note, "fake") and note.fake:
                pass
            else:
                notes.append(note)
        self.notes = notes

    def delete_damage_notes(self):
        notes = []
        for note in self.notes:
            if isinstance(note, Single) and note.type == "damage":
                pass
            else:
                notes.append(note)
        self.notes = notes

    def replace_extended_guide_colors(
        self,
        color_map: dict = {
            "neutral": "green",
            "red": "yellow",
            "green": "green",
            "blue": "green",
            "yellow": "yellow",
            "purple": "yellow",
            "cyan": "green",
            "black": "green",
        },
    ):
        for note in self.notes:
            if not isinstance(note, Guide):
                continue
            note.color = color_map[note.color]

    def replace_extended_ease(self):
        # XXX: Probably better to add an attach tick halfway, then switch ease
        # If anyone wants to PR this, feel free!
        ease_map = {
            "outin": "in",
            "out": "out",
            "linear": "linear",
            "in": "in",
            "inout": "out",
        }
        for note in self.notes:
            if not isinstance(note, (Slide, Guide)):
                continue
            if isinstance(note, Slide):
                for c in note.connections:
                    if hasattr(c, "ease"):
                        c.ease = ease_map[c.ease]
            if isinstance(note, Guide):
                for m in note.midpoints:
                    m.ease = ease_map[m.ease]

    def sort_by_beat(self):
        self.notes = sorted(
            self.notes,
            key=lambda x: (
                x.beat
                if hasattr(x, "beat")
                else (
                    x.connections[0].beat
                    if hasattr(x, "connections")
                    else (
                        x.midpoints[0].beat
                        if hasattr(x, "midpoints")
                        else x.changes[0].beat
                    )
                )
            ),
        )

    # フェードなしガイドの中継点を生成する
    def add_point_without_fade(self):
        for note in self.notes:
            if not isinstance(note, Guide):
                continue
            if note.fade == "none":
                end_point = note.midpoints[-1]
                note.append(
                    GuidePoint(
                        beat=end_point.beat - BEAT_PER_TICK,
                        ease="linear",
                        lane=end_point.lane,
                        size=end_point.size,
                        timeScaleGroup=end_point.timeScaleGroup,
                    )
                )

    def strip_extended_lanes(self, resize_if_possible: bool = False):
        """
        This is a very crude function that deletes any notes with a lane value not supported in the base game.

        resize_if_possible: attempts to resize the note to fit.
        - If not enabled, if the note starts OR ends outside, it'll be deleted.
        - If enabled, a note fully outside is deleted, however a note with any part inside the main lanes will be kept.

        Slides/Guides that have a start/end outside the lanes are fully deleted, otherwise only the connectors are deleted.
        """
        notes = []
        max_lane = 6
        min_lane = -6
        for note in self.notes:
            if isinstance(note, Bpm) or isinstance(note, TimeScaleGroup):
                continue
            if isinstance(note, Single):
                # note.lane 0 (+1/-1 for each lane, based on middle of note, starting at center lane)
                # note.size +0.5 for each lane.
                lane_start = note.lane - note.size
                lane_end = note.lane + note.size
                if lane_start < min_lane:
                    if resize_if_possible and (lane_end > min_lane):
                        # shift the left end, then the middle
                        extra = abs(lane_start - min_lane)
                        note.size -= extra / 2
                        note.lane += extra / 2
                if lane_end > max_lane:
                    if (
                        resize_if_possible
                        and (lane_start < max_lane)
                        and (lane_start >= min_lane)
                    ):
                        # shift the right end, then the middle
                        extra = abs(lane_end - max_lane)
                        note.size -= extra / 2
                        note.lane -= extra / 2
                lane_start = note.lane - note.size
                lane_end = note.lane + note.size
                if lane_start >= min_lane and lane_end <= max_lane:
                    notes.append(note)
            if isinstance(note, Slide):
                connectors = []
                should_add = True
                for i, connector in enumerate(note.connections):
                    lane_start = connector.lane - connector.size
                    lane_end = connector.lane + connector.size
                    added = False
                    if lane_start < min_lane:
                        if resize_if_possible and (lane_end > min_lane):
                            # shift the left end, then the middle
                            extra = abs(lane_start - min_lane)
                            connector.size -= extra / 2
                            connector.lane += extra / 2
                    if lane_end > max_lane:
                        if (
                            resize_if_possible
                            and (lane_start < max_lane)
                            and (lane_start >= min_lane)
                        ):
                            # shift the right end, then the middle
                            extra = abs(lane_end - max_lane)
                            connector.size -= extra / 2
                            connector.lane -= extra / 2
                    lane_start = connector.lane - connector.size
                    lane_end = connector.lane + connector.size
                    if lane_start >= min_lane and lane_end <= max_lane:
                        connectors.append(connector)
                        added = True
                    if (i == 0 or i == len(note.connections) - 1) and not added:
                        should_add = False
                if should_add:
                    notes.append(
                        Slide(
                            critical=note.critical,
                            connections=connectors,
                            type=note.type,
                        )
                    )
            if isinstance(note, Guide):
                midpoints = []
                should_add = True
                for i, midpoint in enumerate(note.midpoints):
                    lane_start = midpoint.lane - midpoint.size
                    lane_end = midpoint.lane + midpoint.size
                    added = False
                    if lane_start < min_lane:
                        if resize_if_possible and (lane_end > min_lane):
                            # shift the left end, then the middle
                            extra = abs(lane_start - min_lane)
                            midpoint.size -= extra / 2
                            midpoint.lane += extra / 2
                    if lane_end > max_lane:
                        if (
                            resize_if_possible
                            and (lane_start < max_lane)
                            and (lane_start >= min_lane)
                        ):
                            # shift the right end, then the middle
                            extra = abs(lane_end - max_lane)
                            midpoint.size -= extra / 2
                            midpoint.lane -= extra / 2
                    lane_start = midpoint.lane - midpoint.size
                    lane_end = midpoint.lane + midpoint.size
                    if lane_start >= min_lane and lane_end <= max_lane:
                        midpoints.append(midpoint)
                        added = True
                    if (i == 0 or i == len(note.midpoints) - 1) and not added:
                        should_add = False
                if should_add:
                    notes.append(
                        Guide(
                            note.color,
                            fade=note.fade,
                            midpoints=midpoints,
                            type=note.type,
                        )
                    )
        self.notes = notes

    # 重なっているノーツをずらす
    def shift(self):
        tmp_notes = []

        # 一旦、中継点灯を含めた全部のノーツを入れたリストを作る（BPM, ソフランは除外）
        for note in self.notes:
            if isinstance(note, Bpm) or isinstance(note, TimeScaleGroup):
                continue
            tmp_notes.append(note)
        tmp_notes = _convert_tmp_notes(tmp_notes)

        # BAR_INTERVALの小節長で分割したリストを作成するために、リストをいくつ作るか計算する
        max_beat = max(tmp_notes, key=lambda x: x.beat).beat

        # BAR_INTERVALの小節長で分割したリストを作成する
        print(max_beat // BAR_INTERVAL)
        split_tmp_notes = [list() for _ in range(int(max_beat // BAR_INTERVAL + 1))]

        # note.beatの値に対応するリストにノーツを入れる
        for note in tmp_notes:
            split_tmp_notes[_calc_notelist_index(note)].append(note)

        for note in self.notes:
            if isinstance(note, Bpm) or isinstance(note, TimeScaleGroup):
                continue

            if isinstance(note, Single):
                _shift_single(note, split_tmp_notes)
            elif isinstance(note, Slide):
                _shift_slide(note, split_tmp_notes)
            elif isinstance(note, Guide):
                _shift_guide(note, split_tmp_notes)
