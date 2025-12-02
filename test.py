from sonolus_converters import sus, LevelData

with open("marbleblue.sus", "r") as f:
    score = sus.load(f)
# LevelData.next_sekai.export("test.leveldata", score, as_compressed=False)
