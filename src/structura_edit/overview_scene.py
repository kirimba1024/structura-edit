from .overview_model import DETAIL_BUDGET, STAGING_BUDGET
from .scene_geometry import add_geometry_steps, remove_geometry


class OverviewScene:
    def __init__(self, plotter):
        self.plotter = plotter
        self.entries = {}
        self.visible = set()
        self.wanted = set()
        self.origin = (0, 0, 0)

    def begin(self, wanted):
        self.wanted = set(wanted)
        self._discard_unneeded()

    def missing(self):
        return self.wanted - self.entries.keys()

    def add_steps(self, key, data, nbytes):
        if key in self.entries or key not in self.wanted:
            return
        nbytes = data.get('geometry_bytes', nbytes)
        if sum(entry[1] for k, entry in self.entries.items() if k in self.wanted) + nbytes > DETAIL_BUDGET:
            raise ValueError("Prepared overview detail exceeds the memory budget")
        if sum(entry[1] for entry in self.entries.values()) + nbytes > DETAIL_BUDGET + STAGING_BUDGET:
            raise ValueError("Overview staging exceeds the memory budget")
        lower = data["origin"]
        actors, complete = [], False
        try:
            for actor in add_geometry_steps(self.plotter, data):
                actors.append(actor)
                actor.SetPosition(*(p - o for p, o in zip(lower, self.origin)))
                actor.SetVisibility(False)
                actor.SetPickable(False)
                yield True
            self.entries[key] = actors, nbytes, lower
            complete = True
        finally:
            if not complete:
                remove_geometry(self.plotter, actors)

    def publish(self, origin):
        if self.missing():
            return False
        self.visible = self.wanted.copy()
        self._discard_unneeded()
        self.rebase(origin)
        for key in self.visible:
            for actor in self.entries[key][0]:
                actor.SetVisibility(True)
        return True

    def rebase(self, origin):
        self.origin = tuple(origin)
        for actors, _, lower in self.entries.values():
            for actor in actors:
                actor.SetPosition(*(p - o for p, o in zip(lower, self.origin)))

    def cancel(self):
        self.wanted = self.visible.copy()
        self._discard_unneeded()

    def _discard_unneeded(self):
        for key in self.entries.keys() - (self.wanted | self.visible):
            actors, _, _ = self.entries.pop(key)
            remove_geometry(self.plotter, actors)

    def clear(self):
        self.wanted.clear()
        self.visible.clear()
        self._discard_unneeded()
