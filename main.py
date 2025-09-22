from sonolus_converters import LevelData, scp, detect, usc, sus
from pathlib import Path

levels, tmpdir = scp.load_levels_from_scp(Path("test.scp"))

for lvl in levels[:1]:  # Extract and convert the first LevelData to USC
    with open(lvl["score"], "rb") as f:
        b = f.read()
        f.seek(0)
        score = LevelData.pjsekai.load(f)
        score.validate()
    valid, is_sus, is_usc, is_leveldata, is_compressed, leveldata_type = detect(b)
    usc.export("test.usc", score)
    with open("test.usc", "rb") as f:
        score2 = usc.load(f)
    sus.export("test.sus", score2)

tmpdir.cleanup()
