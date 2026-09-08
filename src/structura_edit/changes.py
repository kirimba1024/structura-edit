from dataclasses import dataclass
from itertools import product
from math import prod
from numbers import Integral
from typing import Optional, Tuple

from structura_core.nbt import Position

from .cell_data import CellData
from .entity_data import EntityData


class StaleChangeError(ValueError):
    pass


def _position(value):
    value = tuple(value)
    if len(value) != 3 or any(isinstance(v, bool) or not isinstance(v, Integral) for v in value):
        raise ValueError("Coordinates must be three integers")
    return tuple(int(v) for v in value)


@dataclass(frozen=True)
class Selection:
    lower: Position
    upper: Position

    def __post_init__(self):
        object.__setattr__(self, "lower", _position(self.lower))
        object.__setattr__(self, "upper", _position(self.upper))
        if any(lo < 0 for lo in self.lower):
            raise ValueError("Outside document bounds")
        if any(hi <= lo for lo, hi in zip(self.lower, self.upper)):
            raise ValueError("Keep at least 1 block per axis")

    @classmethod
    def from_corners(cls, first, second):
        first, second = _position(first), _position(second)
        return cls(tuple(min(a, b) for a, b in zip(first, second)),
                   tuple(max(a, b) + 1 for a, b in zip(first, second)))

    def shifted(self, offset):
        offset = _position(offset)
        return Selection(tuple(p + d for p, d in zip(self.lower, offset)),
                         tuple(p + d for p, d in zip(self.upper, offset)))

    def expanded(self, amount):
        if isinstance(amount, bool) or not isinstance(amount, Integral):
            raise ValueError("Selection step must be an integer")
        return Selection(tuple(p - amount for p in self.lower), tuple(p + amount for p in self.upper))

    @property
    def volume(self):
        return prod(hi - lo for lo, hi in zip(self.lower, self.upper))

    def __contains__(self, position):
        return all(lo <= v < hi for lo, v, hi in zip(self.lower, position, self.upper))

    def positions(self):
        return product(*(range(lo, hi) for lo, hi in zip(self.lower, self.upper)))


@dataclass(frozen=True)
class _Cell:
    state: str
    variant: Optional[int] = None
    keep_nbt: bool = False
    origin: Optional[Position] = None
    data: Optional[CellData] = None


@dataclass(frozen=True)
class _Delta:
    position: Position
    before: Optional[_Cell]
    after: _Cell


@dataclass(frozen=True)
class EntityDelta:
    key: str
    before: Optional[EntityData]
    after: Optional[EntityData]


@dataclass(frozen=True)
class ChangeSet:
    document_id: str
    base_revision: int
    label: str
    changes: Tuple[_Delta, ...]
    entities: Tuple[EntityDelta, ...] = ()
    resize: object = None

    def __len__(self):
        return len(self.changes) + len(self.entities) + bool(self.resize)

    @property
    def positions(self):
        return tuple(item.position for item in self.changes)

    @property
    def removed_block_entities(self):
        before = {(item.before.origin, item.before.data) for item in self.changes if item.before and item.before.keep_nbt}
        after = {(item.after.origin, item.after.data) for item in self.changes if item.after.keep_nbt}
        return len(before - after)
