from itertools import chain, product
from math import prod
from types import SimpleNamespace

import numpy as np
from structura_core.block_array import BlockArray

from .loading import CHUNK_SIZE, check_preview_budget
from .render_source import RenderSource, preview_session
from .picking import EMPTY
from .height_slice import HeightSlice, slice_sections


ENTITIES = "entities"
LARGE_SCENE_CELLS = 512_000


def section_key(position, span=CHUNK_SIZE):
    return tuple(value // span for value in position)


def affected_sections(positions, size, span=CHUNK_SIZE):
    keys = set()
    for position in positions:
        ranges = (range(max(0, value - 1) // span,
                        min(length - 1, value + 1) // span + 1)
                  for value, length in zip(position, size))
        keys.update(product(*ranges))
    return keys


def changed_positions(before, current):
    if before._state_id == current._state_id:
        return ()
    old, new = before._transition, current._transition
    if new and new[0] == before._state_id:
        positions = new[1]
    elif old and old[0] == current._state_id:
        positions = old[1]
    elif old and new and old[0] == new[0]:
        positions = chain(old[1], new[1])
    else:
        positions = before._cells.keys() | current._cells.keys()
    return (p for p in positions if before._cells.get(p) != current._cells.get(p))


def occupied_sections(session, span):
    base = session._document.source.present
    if not isinstance(base, BlockArray):
        return {section_key(position, span) for position in session.positions()}
    keys = set()
    for lower in product(*(range(0, size, span) for size in session.size)):
        if np.any(base.array[tuple(slice(lo, lo + span) for lo in lower)] >= 0):
            keys.add(section_key(lower, span))
    keys.update(section_key(position, span) for position in session._cells)
    return keys


def prepare_sections(session, change=None, *, previous=None, include_entities=True, previous_entities=True,
                     ghost=None, original=None, height=HeightSlice(), previous_height=HeightSlice()):
    current = preview_session(session, change)
    check_preview_budget(current.size, world=hasattr(current, "dimension"))
    span = CHUNK_SIZE * (4 if prod(current.size) >= LARGE_SCENE_CELLS else 1)
    previous_session = preview_session(*previous) if previous else None
    reset = previous_session is None or previous_session._id != current._id
    reset = reset or previous_session.size != current.size or previous_session.origin != current.origin
    if reset:
        keys = occupied_sections(current, span)
    else:
        keys = affected_sections(changed_positions(previous_session, current), current.size, span)
        if height != previous_height:
            occupied = occupied_sections(current, span)
            keys.update(slice_sections(occupied, previous_height.interval(previous_session),
                                       height.interval(current), current.size, span))
    source = RenderSource(current, height)
    dense = len(keys) * span ** 3 > 32 * CHUNK_SIZE ** 3
    if dense:
        source.prepare_grid()
    offset = ghost.resize.offset if ghost and ghost.resize is not None else (0, 0, 0)
    def shifted(position):
        return tuple(p + d for p, d in zip(position, offset))
    changed = {shifted(position) for position in ghost.positions} if ghost else set()
    removed = {shifted(item.position) for item in ghost.changes if item.after.state.split("[", 1)[0] in EMPTY} if ghost else set()
    original = original or session
    if removed and any(offset):
        from .document_resize import resize_document

        original = original.fork()
        resize_document(original, ghost.resize)
    original = RenderSource(original, height) if removed else None
    if original is not None and dense:
        original.prepare_grid()
    sections = {}
    ghosts = {}
    for key in sorted(keys):
        lower = tuple(value * span for value in key)
        upper = tuple(min(value + span, length) for value, length in zip(lower, current.size))
        start = tuple(max(0, value - 1) for value in lower)
        stop = tuple(min(value + 1, length) for value, length in zip(upper, current.size))
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
    if reset or height != previous_height or include_entities != previous_entities or previous_session._entities != current._entities:
        records = source.entity_records() if include_entities else {}
        entities = SimpleNamespace(size=(1, 1, 1), palette=["minecraft:air"],
                                   palette_raw=[], present={}, block_nbt={},
                                   entities=list(records.values()), entity_keys=tuple(records))
        sections[ENTITIES] = entities, (0, 0, 0), None
    return dict(sections=sections, reset=reset, ghosts=ghosts)
