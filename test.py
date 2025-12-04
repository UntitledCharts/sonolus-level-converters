from sonolus_converters import sus, usc, LevelData

with open("flicks_test.sus", "r") as f:
    score = sus.load(f)
