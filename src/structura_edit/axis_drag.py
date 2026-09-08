from dataclasses import dataclass
from math import copysign, floor

import numpy as np


def axis_parameter(ray, anchor, axis, normal):
    origin, direction = (np.asarray(value, dtype=float) for value in ray)
    denominator = direction @ normal
    if abs(denominator) < np.linalg.norm(direction) * 1e-8:
        return None
    distance = ((anchor - origin) @ normal) / denominator
    if distance < 0:
        return None
    return float((origin + direction * distance - anchor)[axis])


@dataclass
class AxisDrag:
    position: tuple
    anchor: object
    axis: int
    normal: object
    start: float

    @classmethod
    def begin(cls, position, anchor, axis, view_direction, ray):
        normal = np.asarray(view_direction, dtype=float).copy()
        normal /= np.linalg.norm(normal)
        normal[axis] = 0
        if np.linalg.norm(normal) < 0.2:
            return None
        anchor = np.asarray(anchor, dtype=float)
        start = axis_parameter(ray, anchor, axis, normal)
        return cls(position, anchor, axis, normal, start) if start is not None else None

    def moved(self, ray):
        value = axis_parameter(ray, self.anchor, self.axis, self.normal)
        if value is None:
            return None
        delta = value - self.start
        snapped = int(copysign(floor(abs(delta) + 0.5), delta))
        position = list(self.position)
        position[self.axis] += snapped
        return tuple(position)
