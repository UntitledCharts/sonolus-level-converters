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
    LevelData.pjsekai.export(path2, score)


# path = "test.sus"
# file = open(path, "r", encoding="utf8")
# path2 = "LevelData"
# path2 = "ddfcf1d17e6864742fd321a4fe922a55dc7e345f"

# sus_to_leveldata()

# path = "LevelData_Official_Extracted"
# file = open(path, "r", encoding="utf8")
# LevelData.pjsekai.load(file)
