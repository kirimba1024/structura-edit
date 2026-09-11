from copy import copy, deepcopy
from dataclasses import replace

from .loading import check_world_budget
from .source_loading import open_source


def placement_area(session, position, size):
    if not hasattr(session, "world_changes"):
        return None
    upper = tuple(p + s for p, s in zip(position, size))
    if all(0 <= lo < hi <= limit for lo, hi, limit in zip(position, upper, session.size)):
        return None
    lower = tuple(min(0, p) + o for p, o in zip(position, session.origin))
    upper = tuple(max(hi, current) + o for hi, current, o in zip(upper, session.size, session.origin))
    chunks = [(lower[axis] // 16, (upper[axis] - 1) // 16) for axis in (0, 2)]
    radius = max((hi - lo + 1) // 2 for lo, hi in chunks)
    center = ((sum(chunks[0]) // 2) * 16 + 8, (lower[1] + upper[1]) // 2,
              (sum(chunks[1]) // 2) * 16 + 8)
    vertical = max(16, center[1] - lower[1], upper[1] - 1 - center[1])
    if radius > 8 or vertical > 192:
        raise ValueError("Too far from the loaded area. Move closer or load the destination first.")
    check_world_budget(center, radius, vertical)
    return dict(center=center, radius=radius, vertical_radius=vertical)


def load_placement_area(session, placement):
    options = placement_area(session, placement.position, placement.clipboard.size)
    if options is None:
        return session, placement
    changes = copy(session.world_changes)
    changes.patch = changes.patch.copy()
    changes.entities = changes.entities.copy()
    changes.history = deepcopy(changes.history)
    loaded = open_source(session.path, dimension=session.dimension, world_changes=changes, **options)
    offset = tuple(old - new for old, new in zip(session.origin, loaded.origin))
    clipboard = placement.clipboard
    if placement.take:
        if not clipboard.can_take_from(session):
            raise ValueError("The copied blocks changed. Select them and choose Take again.")
        sources = tuple(tuple(p + d for p, d in zip(source, offset)) for source in clipboard.sources)
        for old, new in zip(clipboard.sources, sources):
            if session._portable(session._cell(old), old) != loaded._portable(loaded._cell(new), new):
                raise ValueError("The source changed in the world. Select it and choose Take again.")
        for key, _ in clipboard.entities:
            if session._entities[key].shifted(offset) != loaded._entities.get(key):
                raise ValueError("An object in the source changed. Select it and choose Take again.")
        cells = tuple((p, replace(cell, origin=tuple(v + d for v, d in zip(cell.origin, offset))))
                      if cell.origin is not None else (p, cell) for p, cell in clipboard.cells)
        clipboard = replace(clipboard, origin=loaded.origin, revision=loaded.revision, sources=sources,
                            selection=clipboard.selection.shifted(offset), cells=cells)
    placement = replace(placement, clipboard=clipboard,
                        position=tuple(p + d for p, d in zip(placement.position, offset)), following=False)
    return loaded, placement
