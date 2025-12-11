
import re

# TODO: Detect base sus and chcy sus
def detect(data: str):
    metadata = []
    scoredata = []
    for line in data.splitlines():
        if not line.startswith("#"):
            continue
        line = line.strip()
        match = re.match(r"^#(\w+):\s*(.*)$", line)
        if match:
            scoredata.append(match.groups())
        else:
            metadata.append(tuple(line.split(" ", 1)))
    return '' if metadata and scoredata else None