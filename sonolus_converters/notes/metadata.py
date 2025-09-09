from dataclasses import dataclass


@dataclass
class MetaData:
    title: str
    artist: str
    designer: str
    waveoffset: float
    requests: str
