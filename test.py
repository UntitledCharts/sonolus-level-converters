from sonolus_converters import usc, LevelData

with open("test.usc", "r") as f:
    score = usc.load(f)
LevelData.chart_cyanvas.export("test.ld", score)
with open("test.ld", "rb") as f:
    score = LevelData.chart_cyanvas.load(f)
usc.export("test_out.usc", score)
