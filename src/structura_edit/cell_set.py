from dataclasses import dataclass
from math import floor
from typing import Tuple

from .changes import _position


SECTION_BITS = 4096
SECTION_BYTES = SECTION_BITS // 8
POPULATION = tuple(bin(value).count("1") for value in range(256))


def _span(start, length):
    return (1 << length) - 1 << (SECTION_BITS - start - length)


X_PLANES = tuple(_span(x << 8, 256) for x in range(16))
Y_ROWS = tuple(sum(_span(x << 8 | y << 4, 16) for x in range(16)) for y in range(16))
Z_COLS = tuple(sum(1 << (SECTION_BITS - 1 - (x << 8 | y << 4 | z)) for x in range(16) for y in range(16)) for z in range(16))


def _axis_extent(bits, masks):
    first = next(index for index, mask in enumerate(masks) if bits & mask)
    last = 15 - next(index for index, mask in enumerate(reversed(masks)) if bits & mask)
    return first, last


def _bounds(sections):
    if not sections:
        return (0, 0, 0), (0, 0, 0)
    lower, upper = [], []
    for axis, masks in enumerate((X_PLANES, Y_ROWS, Z_COLS)):
        edge = [((key[axis] << 4) + first, (key[axis] << 4) + last + 1)
                for key, bits in sections
                for first, last in (_axis_extent(int.from_bytes(bits, "big"), masks),)]
        lower.append(min(item[0] for item in edge))
        upper.append(max(item[1] for item in edge))
    return tuple(lower), tuple(upper)


def _from_ints(index):
    sections = tuple((key, bits.to_bytes(SECTION_BYTES, "big")) for key, bits in sorted(index.items()) if bits)
    return CellSet(sections)


def _coerce(selection):
    return selection if isinstance(selection, CellSet) else CellSet.from_box(selection)


@dataclass(frozen=True)
class CellSet:
    sections: Tuple[Tuple[Tuple[int, int, int], bytes], ...] = ()

    def __post_init__(self):
        keys = tuple(key for key, _ in self.sections)
        if keys != tuple(sorted(keys)) or len(set(keys)) != len(keys):
            raise ValueError("Cell set sections must be sorted and unique")
        for _, bits in self.sections:
            if len(bits) != SECTION_BYTES or not any(bits):
                raise ValueError("Cell set sections must be non-empty 4096-bit masks")
        object.__setattr__(self, "_index", {key: int.from_bytes(bits, "big") for key, bits in self.sections})
        object.__setattr__(self, "count", sum(POPULATION[byte] for _, bits in self.sections for byte in bits))
        lower, upper = _bounds(self.sections)
        object.__setattr__(self, "lower", lower)
        object.__setattr__(self, "upper", upper)

    @property
    def volume(self):
        return self.count

    def __bool__(self):
        return bool(self.sections)

    def __contains__(self, position):
        try:
            x, y, z = position
            bits = self._index.get((x >> 4, y >> 4, z >> 4))
            index = (x & 15) << 8 | (y & 15) << 4 | z & 15
        except TypeError:
            return tuple(floor(value) for value in position) in self
        return bits is not None and bits >> (SECTION_BITS - 1 - index) & 1 == 1

    def positions(self):
        for (sx, sy, sz), bits in self.sections:
            base = sx << 4, sy << 4, sz << 4
            remaining = int.from_bytes(bits, "big")
            while remaining:
                high = remaining.bit_length() - 1
                index = SECTION_BITS - 1 - high
                yield base[0] + (index >> 8), base[1] + (index >> 4 & 15), base[2] + (index & 15)
                remaining ^= 1 << high

    @classmethod
    def from_box(cls, selection):
        lower, upper = selection.lower, selection.upper
        sections = []
        for sx in range(lower[0] >> 4, (upper[0] - 1 >> 4) + 1):
            for sy in range(lower[1] >> 4, (upper[1] - 1 >> 4) + 1):
                for sz in range(lower[2] >> 4, (upper[2] - 1 >> 4) + 1):
                    start = sx << 4, sy << 4, sz << 4
                    x0, y0, z0 = (max(lo - base, 0) for lo, base in zip(lower, start))
                    x1, y1, z1 = (min(hi - base, 16) for hi, base in zip(upper, start))
                    block = sum(_span(x << 8 | y << 4 | z0, z1 - z0) for x in range(x0, x1) for y in range(y0, y1))
                    if block:
                        sections.append(((sx, sy, sz), block.to_bytes(SECTION_BYTES, "big")))
        return cls(tuple(sections))

    @classmethod
    def from_positions(cls, positions):
        index = {}
        for position in positions:
            x, y, z = _position(position)
            local = (x & 15) << 8 | (y & 15) << 4 | z & 15
            key = x >> 4, y >> 4, z >> 4
            index[key] = index.get(key, 0) | 1 << (SECTION_BITS - 1 - local)
        return _from_ints(index)

    def shifted(self, offset):
        offset = _position(offset)
        return CellSet.from_positions(tuple(p + d for p, d in zip(position, offset)) for position in self.positions())

    def union(self, other):
        merged = dict(self._index)
        for key, bits in _coerce(other)._index.items():
            merged[key] = merged.get(key, 0) | bits
        return _from_ints(merged)

    def difference(self, other):
        removal = _coerce(other)._index
        return _from_ints({key: bits & ~removal.get(key, 0) for key, bits in self._index.items() if bits & ~removal.get(key, 0)})
