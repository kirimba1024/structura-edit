from dataclasses import dataclass
from math import floor, inf, isfinite, sqrt


EMPTY = {"minecraft:air", "minecraft:cave_air", "minecraft:void_air", "minecraft:structure_void"}


@dataclass(frozen=True)
class Hit:
    position: tuple
    normal: tuple

    @property
    def adjacent(self):
        return tuple(p + n for p, n in zip(self.position, self.normal))


def pick_block(session, origin, direction):
    origin, direction = tuple(origin), tuple(direction)
    if len(origin) != 3 or len(direction) != 3 or not all(isfinite(v) for v in (*origin, *direction)):
        raise ValueError("Ray requires finite three-dimensional vectors")
    length = sqrt(sum(v * v for v in direction))
    if not length:
        return None
    direction = tuple(v / length for v in direction)
    lower, upper = [0, 0, 0], list(session.size)
    entry, end, normal = 0.0, inf, (0, 0, 0)
    for axis, (o, d, lo, hi) in enumerate(zip(origin, direction, lower, upper)):
        if not d:
            if not lo <= o < hi:
                return None
            continue
        near, far = sorted(((lo - o) / d, (hi - o) / d))
        if near >= entry:
            entry = near
            normal = tuple((-1 if d > 0 else 1) if i == axis else 0 for i in range(3))
        end = min(end, far)
    if entry >= end:
        return None
    cell = [min(upper[i] - 1, max(lower[i], floor(origin[i] + direction[i] * (entry + 1e-8)))) for i in range(3)]
    step = [1 if d > 0 else -1 for d in direction]
    delta = [abs(1 / d) if d else inf for d in direction]
    crossing = [(cell[i] + (direction[i] > 0) - origin[i]) / direction[i] if direction[i] else inf for i in range(3)]
    while all(lo <= p < hi for lo, p, hi in zip(lower, cell, upper)):
        state = session.state_at(tuple(cell))
        if state and state.split("[", 1)[0] not in EMPTY:
            return Hit(tuple(cell), normal)
        distance = min(crossing)
        if distance >= end:
            return None
        crossed = [i for i in range(3) if abs(crossing[i] - distance) < 1e-9]
        normal = tuple(-step[i] if i == crossed[0] else 0 for i in range(3))
        for axis in crossed:
            cell[axis] += step[axis]
            crossing[axis] += delta[axis]
    return None
