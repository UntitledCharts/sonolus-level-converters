from sonolus_converters import mmws, sus, usc, LevelData

with open("Master.mmws", "r") as f:
    score = mmws.load(f)

overlaps_score, overlap_count = score.export_overlaps_score()
print(overlap_count)
if overlap_count != 0:
    mmws.export("output.mmws", overlaps_score)
