import json


class SinglePrecisionFloatEncoder(json.JSONEncoder):
    def encode(self, o):
        if isinstance(o, float):
            import numpy as np

            return str(np.float32(o))
        return super().encode(o)


# x = -3.200000047683716
# print(json.dumps(x))  # -3.200000047683716
# print(json.dumps(x, cls=SinglePrecisionFloatEncoder))  # -3.2
