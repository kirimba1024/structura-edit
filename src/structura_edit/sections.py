from itertools import chain, product
from types import SimpleNamespace

import numpy as np

from .loading import CHUNK_SIZE, check_preview_budget
from .render_source import RenderSource, preview_session
from .picking import EMPTY


ENTITIES = "entities"


def section_key(position):
    return tuple(value // CHUNK_SIZE for value in position)


def affected_sections(positions, size):
    keys = set()
    for position in positions:
        ranges = (range(max(0, value - 1) // CHUNK_SIZE,
                        min(length - 1, value + 1) // CHUNK_SIZE + 1)
                  for value, length in zip(position, size))
        keys.update(product(*ranges))
    return keys


def changed_positions(before, current):
    if before._state_id == current._state_id:
        return ()
    old, new = before._transition, current._transition
    if new and new[0] == before._state_id:
        changes = new[1].changes
    elif old and old[0] == current._state_id:
        changes = old[1].changes
    elif old and new and old[0] == new[0]:
        changes = chain(old[1].changes, new[1].changes)
    else:
        changes = None
    if changes is None:
        positions = before._cells.keys() | current._cells.keys()
    else:
        positions = (delta.position for delta in changes)
    return (p for p in positions if before._cells.get(p) != current._cells.get(p))


def prepare_sections(session, change=None, *, previous=None, include_entities=True, previous_entities=True, ghost=None, original=None):
    check_preview_budget(session.size)
    current = preview_session(session, change)
    reset = previous is None or previous[0]._id != session._id
    if reset:
        keys = {section_key(position) for position in current.positions()}
    else:
        before = preview_session(*previous)
        keys = affected_sections(changed_positions(before, current), session.size)
    source = RenderSource(current)
    changed = set(ghost.positions) if ghost else set()
    removed = {item.position for item in ghost.changes if item.after.state.split("[", 1)[0] in EMPTY} if ghost else set()
    original = RenderSource(original or session) if removed else None
    sections = {}
    ghosts = {}
    for key in sorted(keys):
        lower = tuple(value * CHUNK_SIZE for value in key)
        upper = tuple(min(value + CHUNK_SIZE, length) for value, length in zip(lower, session.size))
        start = tuple(max(0, value - 1) for value in lower)
        stop = tuple(min(value + 1, length) for value, length in zip(upper, session.size))
        bounds = tuple(tuple(value - origin for value, origin in zip(bound, start)) for bound in (lower, upper))
        region = source.region(start, stop)
        if changed:
            local = {p for p in region.present if tuple(v + lo for v, lo in zip(p, start)) in changed}
            if local:
                after = SimpleNamespace(**vars(region))
                after.emit_mask = np.zeros(region.size, dtype=bool)
                after.emit_mask[tuple(np.asarray(list(local)).T)] = True
                region.emit_mask = ~after.emit_mask
                before = original.region(start, stop) if original else None
                if before is not None:
                    before.emit_mask = np.zeros(region.size, dtype=bool)
                    for p in before.present:
                        if tuple(v + lo for v, lo in zip(p, start)) in removed:
                            before.emit_mask[p] = True
                ghosts[key] = after, before
        sections[key] = region, start, bounds
    if reset or include_entities != previous_entities:
        entities = SimpleNamespace(size=(1, 1, 1), palette=["minecraft:air"],
                                   palette_raw=[], present={}, block_nbt={},
                                   entities=list(source.base.entities) if include_entities else [])
        sections[ENTITIES] = entities, (0, 0, 0), None
    return dict(sections=sections, reset=reset, ghosts=ghosts)
