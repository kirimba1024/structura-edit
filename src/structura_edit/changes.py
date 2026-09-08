from dataclasses import dataclass
from itertools import product
from math import prod
from numbers import Integral
from typing import Optional, Tuple

from structura_core.nbt import Position

from .cell_data import CellData


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
        if any(lo < 0 or hi <= lo for lo, hi in zip(self.lower, self.upper)):
            raise ValueError("Selection bounds must satisfy 0 <= lower < upper")

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
class ChangeSet:
    document_id: str
    base_revision: int
    label: str
    changes: Tuple[_Delta, ...]

    def __len__(self):
        return len(self.changes)

    @property
    def positions(self):
        return tuple(item.position for item in self.changes)

    @property
    def removed_block_entities(self):
        before = {(item.before.origin, item.before.data) for item in self.changes if item.before and item.before.keep_nbt}
        after = {(item.after.origin, item.after.data) for item in self.changes if item.after.keep_nbt}
        return len(before - after)
