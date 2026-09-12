from math import floor

import numpy as np

from .height_slice import HeightSlice
from .map_environment import MapEnvironment
from .map_projection import cave_view, depth_axis, slice_bounds
from .picking import Hit, pick_block


def pick_map_block(session, position, view, cut=None, cave_y=None, height=HeightSlice()):
    axis = depth_axis(view)
    if any(not 0 <= position[i] < session.size[i] for i in range(3) if i != axis):
        return None
    if cave_view(view, cut, cave_y):
        x, z = floor(position[0]), floor(position[2])
        lower, upper = height.interval(session)
        names = [session.state_at((x, y, z)) if lower <= y < upper else None for y in range(session.size[1])]
        palette = list(dict.fromkeys(name.split("[", 1)[0] for name in names if name))
        indices = {name: index for index, name in enumerate(palette)}
        column = np.asarray([indices[name.split("[", 1)[0]] if name else -1 for name in names], np.int32)
        environment = MapEnvironment(column.reshape(1, -1, 1), palette)
        values, heights = environment.floor(cave_y)
        return Hit((x, int(heights[0, 0]), z), (0, 1, 0)) if values[0, 0, 0] >= 0 else None
    lower, upper = slice_bounds(session.size, cut, view)
    if lower >= upper:
        return None
    positive = view in ("top", "south", "east")
    origin = list(position)
    origin[axis] = upper - 1e-7 if positive else lower + 1e-7
    direction = tuple((-1 if positive else 1) if i == axis else 0 for i in range(3))
    return pick_block(session, origin, direction, height)
