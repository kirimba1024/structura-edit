from dataclasses import dataclass, field, replace
from functools import lru_cache

from .cell_data import detached_cell
from .changes import _Cell


@lru_cache(maxsize=4096)
def _plain_cell(state, keep_nbt):
    return _Cell(state, keep_nbt=keep_nbt)


def merge_delta(patch, key, before, after):
    baseline = patch[key][0] if key in patch else before
    if baseline == after:
        patch.pop(key, None)
    else:
        patch[key] = baseline, after


@dataclass
class SavedChanges:
    origin: tuple
    size: tuple
    blocks: dict = field(default_factory=dict)
    entities: dict = field(default_factory=dict)

    def dirty(self, session):
        return bool(self.blocks or self.entities or self.origin != session.origin or self.size != session.size)

    def updated(self, session, change, *, reverse=False):
        result = SavedChanges(self.origin, self.size, self.blocks.copy(), self.entities.copy())
        origin = session.origin
        if reverse and change.resize is not None:
            origin = tuple(o + d for o, d in zip(origin, change.resize.offset))
        for delta in change.changes:
            values = []
            for cell in (delta.before, delta.after):
                if cell is not None:
                    position = delta.position
                    if reverse and change.resize is not None:
                        offset = change.resize.offset
                        position = tuple(p + d for p, d in zip(position, offset))
                        cell = replace(cell, origin=tuple(p + d for p, d in zip(cell.origin, offset))
                                       if cell.origin is not None else None)
                    cell = detached_cell(session._document.source, cell, position)
                    cell = (_plain_cell(cell.state, cell.keep_nbt) if cell.data is None
                            else replace(cell, origin=None, variant=None))
                values.append(cell)
            before, after = reversed(values) if reverse else values
            merge_delta(result.blocks, tuple(p + o for p, o in zip(delta.position, origin)), before, after)
        for delta in change.entities:
            values = [value.shifted(origin) if value is not None and any(origin) else value
                      for value in (delta.before, delta.after)]
            before, after = reversed(values) if reverse else values
            merge_delta(result.entities, delta.key, before, after)
        return result
