from typing import Union, IO
import os
import gzip
import json
import io
import re


def detect(data: Union[os.PathLike, IO[bytes], bytes]):
    if isinstance(data, os.PathLike):
        with open(data, "rb") as f:
            data = f.read()
    elif isinstance(data, IO):
        data = data.read()

    leveldata = None
    sus = None
    usc = None

    # haha gzip
    if data[:2] == b"\x1f\x8b":
        sus = False
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(data), mode="rb", mtime=0) as gz:
                leveldata = True
                level_data = json.load(gz)
        except (gzip.BadGzipFile, json.JSONDecodeError) as e:
            leveldata = False
    else:
        try:
            level_data = json.loads(data.decode("utf-8"))
            sus = False
            if len(level_data.keys()) == 2:
                if "usc" in level_data:
                    leveldata = False
                    usc = True
                elif "entities" in level_data:
                    usc = False
                    leveldata = True
                else:
                    usc = False
                    leveldata = False
        except (UnicodeDecodeError, json.JSONDecodeError):
            usc = False
            leveldata = False

            metadata = []
            scoredata = []
            for line in data.decode().splitlines():
                if not line.startswith("#"):
                    continue
                line = line.strip()
                match = re.match(r"^#(\w+):\s*(.*)$", line)
                if match:
                    scoredata.append(match.groups())
                else:
                    metadata.append(tuple(line.split(" ", 1)))

            if metadata and scoredata:
                sus = True
            else:
                sus = False

    if leveldata:
        print("Detected level data")
        if not any(e.get("archetype") == "TimeScaleGroup" for e in data["entities"]):
            extended = False
        else:
            extended = True
        if extended:
            print("Detected a extended LevelData: ChCy, US, or NextSekai/PySekai")
        else:
            print("Detected a normal LevelData: PJSekai")
    elif usc:
        print("Detected MMW4CC .usc file")
    elif sus:
        print("Detected .sus file")
    else:
        print("File type not detected")
