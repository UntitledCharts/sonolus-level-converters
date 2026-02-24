from sonolus_converters import mmws, sus, usc, LevelData

with open("o.sus", "r") as f:
    score = sus.load(f)

overlaps_score, overlap_count = score.export_overlaps_score()
print(overlap_count)
if overlap_count != 0:
    LevelData.export("LevelData", overlaps_score)
