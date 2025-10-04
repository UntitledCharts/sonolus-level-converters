import json

import numpy as np


class SinglePrecisionFloatEncoder(json.JSONEncoder):
    def encode(self, o):
        if isinstance(o, float):
            return str(np.float32(o))
        return super().encode(o)


# x = -3.200000047683716
# print(json.dumps(x))  # -3.200000047683716
# print(json.dumps(x, cls=SinglePrecisionFloatEncoder))  # -3.2
