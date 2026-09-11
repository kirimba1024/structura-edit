from copy import copy
from dataclasses import dataclass, replace

from amulet_nbt import IntTag, ListTag
from structura_core.entity_positions import shift_entity

from .changes import _position
from .document import copy_structure
from .loading import check_preview_budget


@dataclass(frozen=True)
class DocumentResize:
    before: tuple
    after: tuple
    offset: tuple


def placement_extent(session, position, size):
    upper = tuple(p + s for p, s in zip(position, size))
    if hasattr(session, "world_changes"):
        session.select((position, upper))
        return None
    lower = tuple(min(0, value) for value in position)
    high = tuple(max(value, current) for value, current in zip(upper, session.size))
    if lower == (0, 0, 0) and high == session.size:
        return None
    dimensions = tuple(hi - lo for lo, hi in zip(lower, high))
    check_preview_budget(dimensions)
    return DocumentResize(session.size, dimensions, tuple(-v for v in lower))


def check_resize(session, resize):
    if resize is None:
        return (0, 0, 0), session.size
    if hasattr(session, "world_changes") or resize.before != session.size:
        raise ValueError("Invalid document resize")
    size, offset = _position(resize.after), _position(resize.offset)
    if any(d < 0 or old + d > new for old, new, d in zip(session.size, size, offset)):
        raise ValueError("Resize must contain the existing schematic")
    check_preview_budget(size)
    return tuple(-d for d in offset), tuple(s - d for s, d in zip(size, offset))


def resize_document(session, resize, *, reverse=False):
    if resize is None:
        return
    size = resize.before if reverse else resize.after
    offset = tuple(-v for v in resize.offset) if reverse else resize.offset
    document = copy(session._document)
    if offset == (0, 0, 0) and isinstance(document.source.present, dict):
        document.source = copy(document.source)
        document.source.size = size
        document.source.source_origin = document.origin
        session._document = document
        return
    source = copy_structure(document.source)
    def shifted(position):
        return tuple(p + d for p, d in zip(position, offset))
    source.size = size
    source.present = {shifted(position): index for position, index in source.present.items()}
    source.block_nbt = {shifted(position): payload for position, payload in source.block_nbt.items()}
    for payload in source.block_nbt.values():
        for axis, delta in zip("xyz", offset):
            if axis in payload:
                payload[axis] = IntTag(int(payload[axis]) + delta)
    source._block_records = {shifted(position): record for position, record in source._block_records.items()}
    for position, record in source._block_records.items():
        record["pos"] = ListTag([IntTag(v) for v in position])
    source.entities = [shift_entity(record, offset) for record in source.entities]
    document.source = source
    document.origin = tuple(o - d for o, d in zip(document.origin, offset))
    source.source_origin = document.origin
    session._document = document
    session._cells = {shifted(position): replace(cell, origin=shifted(cell.origin) if cell.origin is not None else None)
                      for position, cell in session._cells.items()}
    session._entities = {key: value.shifted(offset) for key, value in session._entities.items()}
