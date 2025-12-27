from typing import Literal
from .mmw_io import Signature


def detect(data: bytes) -> Literal["base", "chcy", "unch"] | None:
    sig = next((sig for sig in Signature if data.startswith(sig.value.encode())), None)
    match sig:
        case Signature.MikuMikuWorld:
            return "base"
        case Signature.MikuMikuWorld4ChartCyanvas:
            return "chcy"
        case Signature.MikuMikuWorld4UntitledChart:
            return "unch"
        case _:
            return None
