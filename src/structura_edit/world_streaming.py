from math import floor
from time import monotonic


class WorldStreaming:
    def __init__(self, world, available):
        self.world = world
        self.available = available
        self.target = self.requested = None
        self.since = 0
        self.identity = None

    def tick(self, now=None):
        world = self.world
        if not world.active:
            self.identity = self.requested = self.target = None
            return
        session = world.document.session
        identity = session.path, session.dimension, session.radius, session.vertical_radius
        if identity != self.identity:
            self.identity, self.requested, self.target = identity, None, None
        position = world.camera_position()
        threshold = max(16, session.radius * 8)
        moved = max(abs(position[axis] - session.center[axis]) for axis in (0, 2)) >= threshold
        vertical = session.vertical_radius is not None and abs(position[1] - session.center[1]) >= max(16, session.vertical_radius / 2)
        if not moved and not vertical:
            self.target = None
            return
        quantum = min(64, max(16, session.radius * 8 // 16 * 16))
        target = tuple(floor(value / quantum + .5) * quantum for value in position)
        now = monotonic() if now is None else now
        if target != self.target:
            self.target, self.since = target, now
        if self.available() and not world.tasks.busy and target != self.requested and now - self.since >= .2:
            self.requested = target
            world.center = target
            world.request()
