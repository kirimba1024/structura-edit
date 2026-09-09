from dataclasses import dataclass
from math import floor

from .changes import _position
from .destination_rule import DestinationRule


@dataclass
class Placement:
    clipboard: object
    position: tuple
    take: bool = False
    following: bool = True
    include_air: bool = False
    keep_placing: bool = False
    destination: DestinationRule = DestinationRule()
    include_blocks: bool = True
    include_entities: bool = True

    @property
    def anchor(self):
        x, _, z = self.clipboard.size
        return x // 2, 0, z // 2

    @property
    def bounds(self):
        return self.position, tuple(p + size for p, size in zip(self.position, self.clipboard.size))

    def plan(self, session):
        from .clipboard_placement import plan_placement

        return plan_placement(session, self.clipboard, (_position(self.position),), take=self.take,
                              include_air=self.include_air, destination=self.destination,
                              include_blocks=self.include_blocks, include_entities=self.include_entities,
                              label="Take" if self.take else "Paste")

    def reason(self, session):
        if session.readonly:
            return "View-only document"
        if not self.include_blocks and (not self.include_entities or not self.clipboard.entities):
            return "Choose Blocks or Entities to place" if not self.include_entities else "No entities in this copy"
        if self.take and not self.clipboard.can_take_from(session):
            return "Source changed · take again"
        from .document_resize import placement_extent

        try:
            placement_extent(session, self.position, self.clipboard.size)
        except ValueError as error:
            return str(error)
        return ""

    def set_position(self, position):
        self.position = _position(position)
        self.following = False

    def nudge(self, offset):
        self.set_position(tuple(p + d for p, d in zip(self.position, _position(offset))))

    def set_clipboard(self, clipboard):
        anchor = self.anchor
        self.clipboard = clipboard
        self.position = tuple(p + old - new for p, old, new in zip(self.position, anchor, self.anchor))

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
