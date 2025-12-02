from sonolus_converters import sus, usc

with open("raw_skills.usc", "r") as f:
    score = usc.load(f)
sus.export("skills.sus", score, allow_extended_lanes=True, delete_damage=False)
with open("skills.sus", "r") as f:
    score = sus.load(f)
usc.export("skills.usc", score)
# LevelData.next_sekai.export("test.leveldata", score, as_compressed=False)
