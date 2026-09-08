import pyvista as pv

from .appearance import ACCENT, GHOST_OPACITY, REMOVAL
from .scene_geometry import add_geometry, remove_geometry
from .scene_overlay import BoundsMarker


class PlacementView:
    def __init__(self, plotter):
        self.plotter = plotter
        self.actors = []
        self.bounds = BoundsMarker(plotter, ACCENT, width=2)
        self.anchor = BoundsMarker(plotter, ACCENT, width=2)
        self.source = BoundsMarker(plotter, REMOVAL, width=1)

    def load(self, geometry):
        actors = add_geometry(self.plotter, geometry)
        self.clear()
        self.actors = actors
        for actor in actors:
            actor.SetPickable(False)
            actor.SetUseBounds(False)
            actor.SetForceOpaque(False)
            actor.GetProperty().SetOpacity(actor.GetProperty().GetOpacity() * GHOST_OPACITY)

    def show(self, placement, reason):
        for actor in self.actors:
            actor.SetPosition(*placement.position)
        self.bounds.set_bounds(placement.bounds)
        color = pv.Color(REMOVAL if reason else ACCENT).float_rgb
        for actor in self.bounds.actors + self.anchor.actors:
            actor.GetProperty().SetColor(color)
        anchor = tuple(p + a + 0.5 for p, a in zip(placement.position, placement.anchor))
        self.anchor.set_bounds((tuple(p - 0.12 for p in anchor), tuple(p + 0.12 for p in anchor)))
        selection = placement.clipboard.selection
        self.source.set_bounds((selection.lower, selection.upper) if placement.take else None)
        self.plotter.render()

    def clear(self):
        remove_geometry(self.plotter, self.actors)
        self.actors = []
        for marker in (self.bounds, self.anchor, self.source):
            marker.set_bounds(None)
