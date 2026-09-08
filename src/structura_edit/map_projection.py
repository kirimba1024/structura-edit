from math import floor


VIEWS = ("top", "north", "west", "bottom", "south", "east")
LABELS = ("Top", "North", "West", "Bottom", "South", "East")


def camera_cut(position, size):
    return tuple(min(length, max(-1, floor(value))) for value, length in zip(position, size))


def slice_bounds(size, cut, view):
    axis = depth_axis(view)
    if cut is None:
        return 0, size[axis]
    if view in ("top", "south", "east"):
        return 0, min(size[axis], max(0, cut[axis] + 1))
    return min(size[axis], max(0, cut[axis])), size[axis]


def depth_axis(view):
    return 1 if view in ("top", "bottom") else 2 if view in ("north", "south") else 0


def project(position, size, view):
    x, y, z = position
    if view in ("top", "bottom"):
        return x, z
    if view in ("north", "south"):
        return x if view == "north" else size[0] - x, size[1] - y
    return z if view == "west" else size[2] - z, size[1] - y


def unproject(point, position, size, view):
    u, v = point
    x, y, z = position
    if view in ("top", "bottom"):
        return u, y, v
    if view in ("north", "south"):
        return u if view == "north" else size[0] - u, size[1] - v, z
    return x, size[1] - v, u if view == "west" else size[2] - u


def plane_size(size, view):
    if view in ("top", "bottom"):
        return size[0], size[2]
    return (size[0], size[1]) if view in ("north", "south") else (size[2], size[1])
