from sonolus_converters import sus, usc, LevelData

with open("master.sus", "r") as f:
    score = sus.load(f)
