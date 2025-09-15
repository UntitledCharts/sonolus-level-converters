from sonolus_converters import sus, usc, LevelData


def usc_to_sus():
    score = usc.load(file)
    score.strip_extended_lanes(True)
    score.add_point_without_fade()
    score.shift()
    sus.export(path2, score)


def sus_to_usc():
    score = sus.load(file)
    usc.export(path2, score)


def sus_to_leveldata():
    score = sus.load(file)
    LevelData.chart_cyanvas.export(path2, score, as_compressed=True)
    LevelData.chart_cyanvas.export(path2, score, as_compressed=False)
    # LevelData.pjsekai.export(path2, score)


path = "test.sus"
file = open(path, "r", encoding="utf8")
path2 = "LevelData"

sus_to_leveldata()

path3 = "chcy_official.scp"
path4 = "output.scp"
from sonolus_converters import scp

scp.replace_first_level(path3, path4, path2 + ".gz")

# path3 = "level.scp"
# path4 = "output.scp"
# from sonolus_converters import scp

# scp.replace_first_level(path3, path4, path2 + ".gz")

# path = "LevelData_Official_Extracted"
# file = open(path, "r", encoding="utf8")
# LevelData.pjsekai.load(file)
