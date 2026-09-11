from collections import deque
from dataclasses import replace
from itertools import product

from .cell_set import CellSet
from .changes import ChangeSet, _Cell, _Delta, _position
from .document_resize import placement_extent
from .picking import EMPTY


def normal_axes(normal):
    normal = _position(normal)
    if sum(abs(v) for v in normal) != 1:
        raise ValueError("Normal must be one axis: ±X, ±Y or ±Z")
    return normal, tuple(i for i, value in enumerate(normal) if not value)


def supported(cell):
    from structura_render.full_cube import is_full_cube_shape

    return bool(cell and not cell.keep_nbt and "[" not in cell.state and is_full_cube_shape(cell.state))


def planar_selection(session, start, normal, *, region=None):
    normal, axes = normal_axes(normal)
    start = _position(start)
    bounds = region or session.select()
    if start not in bounds or not supported(session._cell(start)):
        raise ValueError("Choose a full cube without block entity data")
    state = session.state_at(start)
    pending, seen, selected = deque([start]), set(), set()
    while pending:
        point = pending.popleft()
        if point in seen or point not in bounds:
            continue
        seen.add(point)
        if len(seen) > session.operation_limit:
            raise ValueError("Planar search exceeds the cell budget; select a smaller search region")
        session._check_destination(point)
        cell = session._cell(point)
        if not supported(cell) or cell.state != state:
            continue
        adjacent = tuple(p + n for p, n in zip(point, normal))
        if adjacent in session.select():
            try:
                session._check_destination(adjacent)
            except ValueError:
                continue
            other = session.state_at(adjacent)
            if other and other.split("[", 1)[0] not in EMPTY:
                continue
        elif hasattr(session, "world_changes"):
            continue
        selected.add(point)
        pending.extend(tuple(p + (step if i == axis else 0) for i, p in enumerate(point))
                       for axis in axes for step in (-1, 1))
    if not selected:
        raise ValueError("No exposed full-cube face in the loaded area")
    return CellSet.from_positions(selected)


def plane_cells(session, selection, normal):
    normal, axes = normal_axes(normal)
    session._check_selection(selection)
    axis = next(i for i, value in enumerate(normal) if value)
    if selection.upper[axis] - selection.lower[axis] != 1:
        raise ValueError("Select one flat layer perpendicular to the normal")
    if selection.volume > session.operation_limit:
        raise ValueError("Plane exceeds the cell budget")
    cells = tuple(selection.positions())
    if any(not supported(session._cell(point)) for point in cells):
        raise ValueError("The plane needs default-state full cubes without block entity data")
    return normal, axes, cells


def targets_change(session, targets, label):
    if not targets:
        return ChangeSet(session._id, session.revision, label, ())
    if len(targets) > session.operation_limit:
        raise ValueError("Operation exceeds the cell budget")
    lower = tuple(min(p[i] for p in targets) for i in range(3))
    size = tuple(max(p[i] for p in targets) - lower[i] + 1 for i in range(3))
    resize = placement_extent(session, lower, size)
    changes = []
    for point, after in targets.items():
        session._check_destination(point)
        before = session._cell(point)
        if before != after:
            changes.append(_Delta(point, before, after))
    change = ChangeSet(session._id, session.revision, label, tuple(changes), resize=resize)
    session._check_change(change)
    return change


def extrude(session, selection, normal, depth):
    normal, _, cells = plane_cells(session, selection, normal)
    if type(depth) is not int or depth < 1 or len(cells) * depth > session.operation_limit:
        raise ValueError("Use a positive depth within the cell budget")
    targets = {}
    for point in cells:
        after = replace(session._cell(point), origin=None, variant=None, data=None)
        for step in range(1, depth + 1):
            destination = tuple(p + step * n for p, n in zip(point, normal))
            before = session._cell(destination)
            if before and before.state.split("[", 1)[0] not in EMPTY:
                raise ValueError(f"Extrude destination is occupied at {destination}")
            targets[destination] = after
    return targets_change(session, targets, "Extrude")


def frame(session, selection, normal, target, thickness=1, outside=True):
    _, axes, cells = plane_cells(session, selection, normal)
    if type(thickness) is not int or thickness < 1 or len(cells) * (2 * thickness + 1) ** 2 > session.operation_limit:
        raise ValueError("Frame neighbourhood exceeds the cell budget")
    cell = _Cell(target)
    if not supported(cell):
        raise ValueError("Frame material must be a full cube")
    selected = set(cells)
    offsets = tuple(product(range(-thickness, thickness + 1), repeat=2))
    def neighbours(point):
        return (tuple(p + (a if i == axes[0] else b if i == axes[1] else 0) for i, p in enumerate(point))
                for a, b in offsets)
    boundary = {p for point in cells for p in neighbours(point)} - selected if outside else {
        point for point in cells if any(p not in selected for p in neighbours(point))}
    return targets_change(session, {point: cell for point in boundary}, "Outer frame" if outside else "Inner frame")
