from collections import OrderedDict
from math import sqrt

from .scene_geometry import add_geometry, remove_geometry


class InspectionScene:
    def __init__(self, plotter, limit=16 * 1024**2):
        self.plotter = plotter
        self.limit = limit
        self.entries = OrderedDict()
        self.size = 0
        self.current = None

    def show(self, key, data):
        if key not in self.entries:
            actors = add_geometry(self.plotter, data)
            bounds = [actor.GetBounds() for actor in actors]
            lower = tuple(min(value[axis] for value in bounds) for axis in (0, 2, 4)) if actors else (0, 0, 0)
            upper = tuple(max(value[axis] for value in bounds) for axis in (1, 3, 5)) if actors else lower
            center = tuple((lo + hi) / 2 for lo, hi in zip(lower, upper))
            radius = max(1, sqrt(sum((hi - lo)**2 for lo, hi in zip(lower, upper)))) * 2
            size = data["geometry_bytes"]
            self.entries[key] = actors, center, radius, size
            self.size += size
        self.entries.move_to_end(key)
        if self.current in self.entries and self.current != key:
            for actor in self.entries[self.current][0]:
                actor.SetVisibility(False)
        self.current = key
        actors, center, radius, _ = self.entries[key]
        for actor in actors:
            actor.SetVisibility(True)
        while len(self.entries) > 1 and (self.size > self.limit or len(self.entries) > 32):
            _, (expired, _, _, size) = self.entries.popitem(last=False)
            remove_geometry(self.plotter, expired)
            self.size -= size
        return bool(actors), center, radius

    def clear(self):
        for actors, _, _, _ in self.entries.values():
            remove_geometry(self.plotter, actors)
        self.entries.clear()
        self.size = 0
        self.current = None
