from sonolus_converters import pjsk

score = pjsk.load("input.pjsk", fix_overlaps=False)
pjsk.export("output.pjsk", score, music_id=154)

original = pjsk.load_raw("input.pjsk")
exported = pjsk.load_raw("output.pjsk")

diffs = []
for key in original:
    if key == "$id":
        continue
    if key == "FullComboDataHash":
        continue
    orig_val = original.get(key)
    exp_val = exported.get(key)
    if orig_val != exp_val:
        diffs.append(key)

if not diffs:
    print("roundtrip matches!")
else:
    for key in diffs:
        print(f"DIFF: {key}")
        if key in ("MusicScoreEventDataList", "NoteList", "EventArray"):
            orig_list = original[key]
            exp_list = exported[key]
            print(
                f"  original count: {len(orig_list)}, exported count: {len(exp_list)}"
            )
            for i, (a, b) in enumerate(zip(orig_list, exp_list)):
                if a != b:
                    print(f"  item {i} differs:")
                    for k in set(list(a.keys()) + list(b.keys())):
                        if a.get(k) != b.get(k):
                            print(f"    {k}: {a.get(k)} -> {b.get(k)}")
            if len(orig_list) != len(exp_list):
                print(
                    f"  extra in {'original' if len(orig_list) > len(exp_list) else 'exported'}"
                )
        else:
            print(f"  original: {original.get(key)}")
            print(f"  exported: {exported.get(key)}")
