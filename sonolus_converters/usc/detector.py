import json
from typing import Literal


def detect(data: str | bytes | bytearray) -> Literal["v1", "v2"] | None:
    try:
        usc = json.loads(data)
        if "usc" in usc and "version" in usc:
            match usc["version"]:
                case 1:
                    return "v1"
                case 2:
                    return "v2"
                case _:
                    print(f"Unknown usc version {usc['version']}")
    except json.JSONDecodeError:
        return
