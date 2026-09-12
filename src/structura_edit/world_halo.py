from dataclasses import dataclass
from itertools import product

import numpy as np

from structura_core.world_terrain import existing_chunks, terrain_sections

from .picking import EMPTY


@dataclass(frozen=True)
class WorldHalo:
    origin: tuple
    size: tuple
    palette: tuple
    faces: tuple

    def updated(self, updates):
        if not updates:
            return self
        palette = list(self.palette)
        indices = {state: index for index, state in enumerate(palette)}
        faces = []
        for start, array in self.faces:
            changed = None
            for position, state in updates.items():
                local = tuple(p - s for p, s in zip(position, start))
                if all(0 <= p < n for p, n in zip(local, array.shape)):
                    if changed is None:
                        changed = array.copy()
                    if state not in indices:
                        indices[state] = len(palette)
                        palette.append(state)
                    changed[local] = -1 if state.split("[", 1)[0] in EMPTY else indices[state]
            faces.append((start, array if changed is None else changed))
        return WorldHalo(self.origin, self.size, tuple(palette), tuple(faces))


def halo_updates(session):
    result = {}
    if getattr(session, "_render_halo", None) is not None and hasattr(session, "world_changes"):
        for (dimension, *world), (_, cell) in session.world_changes.patch.items():
            position = tuple(p - o for p, o in zip(world, session.origin))
            if (dimension == session.dimension and all(-1 <= p <= s for p, s in zip(position, session.size))
                    and any(p in (-1, s) for p, s in zip(position, session.size))):
                result[position] = cell.state
    return result


def read_world_halo(directory, origin, size, data_version, *, vertical=False):
    lower = tuple(p - 1 for p in origin)
    upper = tuple(p + s + 1 for p, s in zip(origin, size))
    faces = []
    for axis in range(3):
        for side in (0, 1):
            start, stop = list(lower), list(upper)
            start[axis] = upper[axis] - 1 if side else lower[axis]
            stop[axis] = start[axis] + 1
            faces.append((tuple(start), np.full(tuple(hi - lo for lo, hi in zip(start, stop)), -1, np.int32)))
    columns = set(product(range(lower[0] // 16, (upper[0] - 1) // 16 + 1),
                          range(lower[2] // 16, (upper[2] - 1) // 16 + 1)))
    if not vertical:
        columns = {(x, z) for x, z in columns if x * 16 < origin[0] or x * 16 >= origin[0] + size[0]
                   or z * 16 < origin[2] or z * 16 >= origin[2] + size[2]}
    regions = {(x // 32, z // 32) for x, z in columns}
    columns.intersection_update(existing_chunks(directory, regions=regions))
    palette, indices = [], {}
    def index(state):
        if state.split("[", 1)[0] in EMPTY:
            return -1
        if state not in indices:
            indices[state] = len(palette)
            palette.append(state)
        return indices[state]
    for x, z in sorted(columns):
        for section in terrain_sections(directory, x, z, data_version):
            start = tuple(p * 16 for p in section.position)
            if start[1] >= upper[1] or start[1] + 16 <= lower[1]:
                continue
            mapping = np.asarray([*(index(state) for state in section.palette), -1], np.int32)
            for position, array in faces:
                lo = tuple(max(p, s) for p, s in zip(position, start))
                hi = tuple(min(p + n, s + 16) for p, n, s in zip(position, array.shape, start))
                if all(a < b for a, b in zip(lo, hi)):
                    target = tuple(slice(a - p, b - p) for a, b, p in zip(lo, hi, position))
                    source = tuple(slice(a - p, b - p) for a, b, p in zip(lo, hi, start))
                    array[target] = mapping[section.blocks[source]]
    return WorldHalo(tuple(origin), tuple(size), tuple(palette),
                     tuple((tuple(p - o for p, o in zip(start, origin)), array) for start, array in faces))
