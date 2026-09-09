from structura_core.nbt import parse_state, state_key

from .changes import Selection
from .picking import EMPTY


def _neighbours(position):
    for axis in range(3):
        for step in (-1, 1):
            yield tuple(v + (step if i == axis else 0) for i, v in enumerate(position))


def _boundary(selection):
    if isinstance(selection, Selection):
        lower, upper = selection.lower, selection.upper
        return lambda position: tuple(v in (lo, hi - 1) for v, lo, hi in zip(position, lower, upper))

    def edges(position):
        near = list(_neighbours(position))
        return tuple(any(neighbour not in selection for neighbour in near[axis * 2:axis * 2 + 2]) for axis in range(3))
    return edges


def _shell(selection, thickness):
    edges = _boundary(selection)
    frontier = [position for position in selection.positions() if any(edges(position))]
    shell = set(frontier)
    for _ in range(thickness - 1):
        frontier = [neighbour for position in frontier for neighbour in _neighbours(position)
                    if neighbour in selection and neighbour not in shell]
        shell.update(frontier)
    return shell


def shape_positions(session, selection, form, mask, surface, thickness=1):
    if form not in ("Box", "Walls", "Shell", "Ellipsoid", "Cylinder", "Top surface", "Hollow", "Overlay surface"):
        raise ValueError(f"Unknown shape: {form}")
    mask = state_key(parse_state(mask)) if mask else None
    lower, upper = selection.lower, selection.upper
    center = tuple((lo + hi) / 2 for lo, hi in zip(lower, upper))
    radius = tuple((hi - lo) / 2 for lo, hi in zip(lower, upper))

    def empty(position):
        if any(v < 0 or v >= s for v, s in zip(position, session.size)):
            return True
        state = session.state_at(position)
        return not state or state.split("[", 1)[0] in EMPTY

    top = {}
    if form in ("Top surface", "Overlay surface"):
        for x, y, z in session.positions():
            if (x, y, z) in selection and not empty((x, y, z)):
                top[x, z] = max(y, top.get((x, z), y))
    shell = _shell(selection, thickness) if form == "Hollow" else ()
    edges = _boundary(selection)
    for position in selection.positions():
        if mask:
            state = session.state_at(position)
            if state is None or (state if "[" in mask else state.split("[", 1)[0]) != mask:
                continue
        if surface and (empty(position) or not any(empty(tuple(v + (d if i == axis else 0) for i, v in enumerate(position))) for axis in range(3) for d in (-1, 1))):
            continue
        edge = edges(position)
        if form == "Walls" and not (edge[0] or edge[2]):
            continue
        if form == "Shell" and not any(edge):
            continue
        if form == "Hollow" and position in shell:
            continue
        if form in ("Ellipsoid", "Cylinder"):
            axes = (0, 2) if form == "Cylinder" else (0, 1, 2)
            if sum(((position[i] + 0.5 - center[i]) / radius[i]) ** 2 for i in axes) > 1:
                continue
        if form == "Top surface" and position[1] != top.get((position[0], position[2])):
            continue
        if form == "Overlay surface" and position[1] != top.get((position[0], position[2]), position[1]) + 1:
            continue
        yield position
