from types import SimpleNamespace

import numpy as np


def entity_bounds(records, keys, bank):
    from structura_render.mesh import flat_entity_groups

    result = {}
    with bank.context.activate():
        for key, record in zip(keys, records):
            groups = flat_entity_groups(SimpleNamespace(entities=[record]))
            if groups:
                low = np.min([np.min(points, axis=0) for _, points, _ in groups], axis=0)
                high = np.max([np.max(points, axis=0) for _, points, _ in groups], axis=0)
                result[key] = tuple(low - 0.01), tuple(high + 0.01)
    return result


def ray_distances(bounds, origin, direction):
    bounds = np.asarray(bounds, dtype=float)
    if not len(bounds):
        return np.empty(0)
    origin, direction = np.asarray(origin), np.asarray(direction)
    length = np.linalg.norm(direction)
    if not length:
        return np.full(len(bounds), np.inf)
    direction = direction / length
    moving = np.abs(direction) > 1e-12
    distance = (bounds[:, :, moving] - origin[moving]) / direction[moving]
    near = np.maximum(0, np.min(distance, axis=1).max(axis=1))
    far = np.max(distance, axis=1).min(axis=1)
    outside = ((origin[~moving] < bounds[:, 0, ~moving]) | (origin[~moving] > bounds[:, 1, ~moving])).any(axis=1)
    return np.where((near <= far) & ~outside, near, np.inf)


def nearest_entity(keys, bounds, origin, direction, block=None):
    distances = ray_distances(bounds, origin, direction)
    if not len(distances):
        return None
    index = int(distances.argmin())
    if not np.isfinite(distances[index]):
        return None
    if block is not None:
        block_bounds = [(block.position, tuple(v + 1 for v in block.position))]
        if ray_distances(block_bounds, origin, direction)[0] < distances[index] - 0.01:
            return None
    return keys[index]
