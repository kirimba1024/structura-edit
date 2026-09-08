VIEWS = ("top", "north", "west", "bottom", "south", "east")
LABELS = ("Top", "North", "West", "Bottom", "South", "East")


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
