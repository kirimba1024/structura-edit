from structura_core.nbt import parse_state, state_key

from .changes import Selection
from .picking import EMPTY


def _boundary(selection):
    if isinstance(selection, Selection):
        lower, upper = selection.lower, selection.upper
        return lambda position: tuple(v in (lo, hi - 1) for v, lo, hi in zip(position, lower, upper))

    def edges(position):
        result = []
        for axis in range(3):
            outside = False
            for step in (-1, 1):
                neighbour = tuple(v + (step if i == axis else 0) for i, v in enumerate(position))
                if neighbour not in selection:
                    outside = True
                    break
            result.append(outside)
        return tuple(result)
    return edges


def shape_positions(session, selection, form, mask, surface):
    if form not in ("Box", "Walls", "Shell", "Ellipsoid", "Cylinder", "Top surface"):
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
    if form == "Top surface":
        for x, y, z in session.positions():
            if (x, y, z) in selection and not empty((x, y, z)):
                top[x, z] = max(y, top.get((x, z), y))
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
        if form in ("Ellipsoid", "Cylinder"):
            axes = (0, 2) if form == "Cylinder" else (0, 1, 2)
            if sum(((position[i] + 0.5 - center[i]) / radius[i]) ** 2 for i in axes) > 1:
                continue
        if form == "Top surface" and position[1] != top.get((position[0], position[2])):
            continue
        yield position
