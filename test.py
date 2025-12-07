from sonolus_converters import sus, usc, LevelData

with open("exported.sus", "r") as f:
    score = sus.load(f)
