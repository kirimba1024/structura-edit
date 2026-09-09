from dataclasses import dataclass

from .cell_set import CellSet
from .changes import _position
from .picking import EMPTY


CONNECTED_LIMIT = 2_000_000
MAX_CONNECTED_AREA = 8_000_000
CRITERIA = ("material", "state", "non-air")


@dataclass(frozen=True)
class ConnectedResult:
    cells: object
    criterion: str
    start: tuple


def connected_selection(session, start, *, criterion="material", limit=CONNECTED_LIMIT, progress=None):
    import numpy as np

    start = _position(start)
    if criterion not in CRITERIA:
        raise ValueError("Criterion must be material, state or non-air")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise ValueError("Connected limit must be a positive integer")
    if any(v < 0 or v >= s for v, s in zip(start, session.size)):
        raise ValueError("Pick a block inside the document")
    if session.size[0] * session.size[1] * session.size[2] > MAX_CONNECTED_AREA:
        raise ValueError("Connected select needs a loaded area of at most 8 million cells")
    if progress:
        progress("Connected select", 0, limit)
    grid = _grid(np, session, _groups(session, criterion), progress)
    reached = _flood(np, grid, start, limit, progress)
    return ConnectedResult(_cells(np, reached, session.size), criterion, start)


def _groups(session, criterion):
    groups, ids = {}, {}
    states = list(session._states) + [cell.state for cell in session._cells.values()]
    for state in states:
        if state in ids:
            continue
        if criterion == "state":
            key = state
        elif criterion == "material":
            key = state.split("[", 1)[0]
        else:
            key = "air" if state.split("[", 1)[0] in EMPTY else "block"
        ids[state] = groups.setdefault(key, len(groups) + 1)
    return ids


def _grid(np, session, ids, progress):
    width, height, depth = session.size
    grid = np.zeros((width + 2, height + 2, depth + 2), dtype=np.int32)
    lookup = np.array([ids[state] for state in session._states], dtype=np.int32)
    present = session._document.source.present
    keys = list(present)
    total = len(keys) + len(session._cells)
    for offset in range(0, len(keys), 262_144):
        batch = keys[offset:offset + 262_144]
        columns = np.array(batch, dtype=np.int64).T + 1
        values = np.fromiter((present[position] for position in batch), dtype=np.int64, count=len(batch))
        grid[columns[0], columns[1], columns[2]] = lookup[values]
        if progress:
            progress("Connected select", offset + len(batch), total)
    for position, cell in session._cells.items():
        grid[position[0] + 1, position[1] + 1, position[2] + 1] = ids[cell.state]
    if progress:
        progress("Connected select", total, total)
    return grid


def _flood(np, grid, start, limit, progress):
    flat = int(np.ravel_multi_index((start[0] + 1, start[1] + 1, start[2] + 1), grid.shape))
    seed = int(grid.ravel()[flat])
    if seed == 0:
        raise ValueError("Pick a non-empty block")
    match = np.ascontiguousarray(grid == seed).ravel().tobytes()
    reached = bytearray(len(match))
    reached[flat] = 1
    strides = (1, grid.shape[2], grid.shape[1] * grid.shape[2])
    frontier, visited, checked = [flat], 1, 0
    while frontier:
        following = []
        for index in frontier:
            for stride in strides:
                for delta in (stride, -stride):
                    neighbour = index + delta
                    if match[neighbour] and not reached[neighbour]:
                        reached[neighbour] = 1
                        visited += 1
                        if visited > limit:
                            raise ValueError(
                                f"Connected selection exceeds {limit:,} cells; use a stricter criterion such as Exact state")
                        following.append(neighbour)
            checked += 1
            if not checked & 0xFFFF and progress:
                progress("Connected select", visited, limit)
        frontier = following
    return reached


def _cells(np, reached, size):
    width, height, depth = size
    flags = np.frombuffer(bytes(reached), dtype=np.uint8).reshape(width + 2, height + 2, depth + 2)
    sections = []
    for sx in range(width + 15 >> 4):
        for sy in range(height + 15 >> 4):
            for sz in range(depth + 15 >> 4):
                cube = flags[1 + sx * 16:1 + min((sx + 1) * 16, width),
                              1 + sy * 16:1 + min((sy + 1) * 16, height),
                              1 + sz * 16:1 + min((sz + 1) * 16, depth)]
                if not cube.any():
                    continue
                block = np.zeros((16, 16, 16), dtype=np.uint8)
                block[:cube.shape[0], :cube.shape[1], :cube.shape[2]] = cube
                sections.append(((sx, sy, sz), np.packbits(block).tobytes()))
    return CellSet(tuple(sections))
