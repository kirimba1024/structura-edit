import numpy as np

from .map_projection import camera_cut


class MapEnvironment:
    def __init__(self, state, palette):
        from structura_render.block_geometry import shape_is_occluder

        opaque = np.asarray([shape_is_occluder(name) for name in palette] + [False])[state]
        self.roofs = np.where(opaque.any(axis=1), state.shape[1] - 1 - opaque[:, ::-1, :].argmax(axis=1), -1)
        self.state, self.opaque = state, opaque
        self.floor_cache = None
        self.floors = None
        self.size = state.shape
        self.cave = False

    def cut(self, position):
        x, y, z = camera_cut(position, self.size)
        if not 0 <= x < self.size[0] or not 0 <= z < self.size[2]:
            return None
        roof = self.roofs[max(0, x - 2):x + 3, max(0, z - 2):z + 3]
        coverage = np.mean(roof > y + 1)
        self.cave = bool(coverage >= (0.4 if self.cave else 0.72))
        return (x, y, z) if self.cave else None

    def floor(self, y):
        y = min(self.size[1] - 1, max(0, int(y)))
        if self.floor_cache is not None and self.floor_cache[0] == y:
            return self.floor_cache[1:]
        if self.size[1] < 3:
            return np.full((self.size[0], 1, self.size[2]), -1, dtype=self.state.dtype), np.zeros((self.size[2], self.size[0]))
        opaque = self.opaque
        if self.floors is None:
            floors = opaque[:, :-2, :] & ~opaque[:, 1:-1, :] & ~opaque[:, 2:, :]
            floors &= self.roofs[:, None, :] > np.arange(self.size[1] - 2)[None, :, None] + 2
            self.floors = np.ascontiguousarray(floors.transpose(0, 2, 1))
        below = self.floors[..., :min(y + 1, self.floors.shape[-1])]
        index = below.shape[-1] - 1 - below[..., ::-1].argmax(axis=-1)
        valid = below.any(axis=-1)
        above = self.floors[..., y + 1:y + 9]
        if above.shape[-1]:
            higher = y + 1 + above.argmax(axis=-1)
            choose = above.any(axis=-1) & (~valid | (higher - y < y - index))
            index = np.where(choose, higher, index)
            valid |= choose
        values = np.take_along_axis(self.state, index[:, None, :], axis=1)
        values = np.where(valid[:, None, :], values, -1)
        heights = np.where(valid, index, 0).T
        self.floor_cache = y, values, heights
        return values, heights
