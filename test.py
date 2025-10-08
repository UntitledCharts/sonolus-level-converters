from sonolus_converters import usc, sus, LevelData

# # Test chcy loading
# with open("test.usc", "r") as f:
#     score1 = usc.load(f)
# LevelData.chart_cyanvas.export("test.ld", score1)
# with open("test.ld", "rb") as f:
#     score2 = LevelData.chart_cyanvas.load(f)
# score1.compare(score2)
# usc.export("test_out.usc", score2)

# Test pjsk (ld) loading
with open("test.usc", "r") as f:
    score1 = usc.load(f)
sus.export("test.sus", score1)
with open("test.sus", "r") as f:
    score1 = sus.load(f)
LevelData.pjsekai.export("test_pjsk.ld", score1)
with open("test_pjsk.ld", "rb") as f:
    score2 = LevelData.pjsekai.load(f)
sus.export("test_out.sus", score2)
