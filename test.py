from sonolus_converters import usc, LevelData

with open("test.usc", "r") as f:
    score1 = usc.load(f)
LevelData.chart_cyanvas.export("test.ld", score1)
with open("test.ld", "rb") as f:
    score2 = LevelData.chart_cyanvas.load(f)
score1.compare(score2)
usc.export("test_out.usc", score2)
