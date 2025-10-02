from sonolus_converters import LevelData, scp, detect, usc
from pathlib import Path
import os, re, json

levels, tmpdir = scp.load_levels_from_scp(Path("test.scp2"))
output_dir = Path("out")


def sanitize_level_name(name: str) -> str:
    sanitized_name = re.sub(r"[^a-zA-Z0-9 _-]", "", name)
    return sanitized_name


for lvl in levels:
    level_name: str = sanitize_level_name(lvl["data"].get("title", "unknown"))
    output_files_dir = output_dir / level_name
    output_files_dir.mkdir(parents=True, exist_ok=True)
    with open(lvl["score"], "rb") as f:
        score_data = f.read()
        f.seek(0)
        score = LevelData.chart_cyanvas.load(f)
    valid, is_sus, is_usc, is_leveldata, is_compressed, leveldata_type = detect(
        score_data
    )

    score_file = output_files_dir / "RawLevelData.json.gz"
    with open(score_file, "wb") as f:
        f.write(score_data)

    usc.export(output_files_dir / "score.usc", score)

    for file_type in ["audio", "preview", "cover"]:
        file_path: Path | None = lvl.get(file_type)
        if file_path:
            new_path = output_files_dir / file_type
            os.rename(file_path, new_path)
            print(f"Moved {file_path} to {new_path}")
    with open(output_files_dir / "level.json", "w", encoding="utf-8") as f:
        json.dump(lvl["data"], f, indent=4)
tmpdir.cleanup()
