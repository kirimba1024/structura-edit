from dataclasses import dataclass
from math import floor

from .changes import _position


@dataclass
class Placement:
    clipboard: object
    position: tuple
    take: bool = False
    following: bool = True
    include_air: bool = False

    @property
    def anchor(self):
        x, _, z = self.clipboard.size
        return x // 2, 0, z // 2

    @property
    def bounds(self):
        return self.position, tuple(p + size for p, size in zip(self.position, self.clipboard.size))

    def reason(self, session):
        if session.readonly:
            return "This document is view-only"
        if self.take and (session._id != self.clipboard.document_id or session.revision != self.clipboard.revision):
            return "The source changed; take a fresh selection"
        lower, upper = self.bounds
        if any(lo < 0 or hi > size for lo, hi, size in zip(lower, upper, session.size)):
            return "Outside document bounds · adjust XYZ"
        return ""

    def set_position(self, position):
        self.position = _position(position)
        self.following = False

    def nudge(self, offset):
        self.set_position(tuple(p + d for p, d in zip(self.position, _position(offset))))

    def follow(self, origin, direction, hit=None):
        if not self.following:
            return False
        if hit is not None:
            position = [p - a for p, a in zip(hit.position, self.anchor)]
            for axis, normal in enumerate(hit.normal):
                if normal:
                    position[axis] = hit.position[axis] + (1 if normal > 0 else -self.clipboard.size[axis])
        else:
            if abs(direction[1]) < 1e-8:
                return False
            distance = (self.position[1] - origin[1]) / direction[1]
            if distance <= 0:
                return False
            position = [floor(o + distance * d) - a for o, d, a in zip(origin, direction, self.anchor)]
            position[1] = self.position[1]
        position = tuple(position)
        if position == self.position:
            return False
        self.position = position
        return True
