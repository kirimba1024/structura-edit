import numpy as np
import pyvista as pv

from .picking import pick_block
from .loading import replacement_sizes
from .appearance import GHOST_OPACITY, REMOVAL, REMOVAL_OPACITY
from .scene_geometry import add_geometry


class Scene:
    def __init__(self, plotter):
        self.plotter = plotter
        self.sections = {}
        self.section_bytes = {}
        self.ghost_actors = {}
        self.removed_bytes = {}
        self.display_revision = None

    @property
    def actors(self):
        return [actor for actors in self.sections.values() for actor in actors]

    def clear(self):
        self._remove(self.actors)
        self.sections.clear()
        self.section_bytes.clear()
        self.removed_bytes.clear()
        self.display_revision = None

    def replace(self, data, revision):
        sizes = replacement_sizes(data, self.section_bytes)
        replacements = {}
        try:
            for key, section in data["sections"].items():
                replacements[key] = self._add_section(section)
        except Exception:
            self._remove(actor for actors in replacements.values() for actor in actors)
            raise
        if data["reset"]:
            self._remove(self.actors)
            self.sections.clear()
            self.removed_bytes.clear()
        else:
            for key in replacements:
                self._remove(self.sections.get(key, []))
        self.sections.update(replacements)
        self.removed_bytes.update((key, section.get("layers", {}).get("removed", {}).get("geometry_bytes", 0))
                                  for key, section in data["sections"].items())
        self.section_bytes = sizes
        self.display_revision = revision

    def _remove(self, actors):
        for actor in actors:
            self.ghost_actors.pop(actor, None)
            self.plotter.remove_actor(actor, reset_camera=False, render=False)

    def _add_section(self, data):
        actors = add_geometry(self.plotter, data)
        try:
            for name, layer in data.get("layers", {}).items():
                additions = self._add_section(layer)
                actors.extend(additions)
                for actor in additions:
                    prop = actor.GetProperty()
                    self.ghost_actors[actor] = name, prop.GetOpacity(), actor.GetForceOpaque()
                    actor.SetForceOpaque(False)
                    if name == "removed":
                        actor.SetTexture(None)
                        prop.SetRepresentationToWireframe()
                        prop.SetColor(pv.Color(REMOVAL).float_rgb)
                        prop.SetOpacity(REMOVAL_OPACITY)
                        prop.LightingOff()
                    else:
                        prop.SetOpacity(prop.GetOpacity() * GHOST_OPACITY)
        except Exception:
            self._remove(actors)
            raise
        return actors

    def accept_preview(self):
        removed = set()
        for actor, (kind, opacity, opaque) in self.ghost_actors.items():
            if kind == "removed":
                removed.add(actor)
            else:
                actor.GetProperty().SetOpacity(opacity)
                actor.SetForceOpaque(opaque)
        self._remove(removed)
        self.ghost_actors.clear()
        for key, size in self.removed_bytes.items():
            self.section_bytes[key] -= size
        self.removed_bytes.clear()
        self.sections = {key: [actor for actor in actors if actor not in removed] for key, actors in self.sections.items()}
        self.plotter.render()

    def hit_at(self, session, point):
        return pick_block(session, *self.ray_at(point))

    def ray_at(self, point):
        renderer = self.plotter.renderer
        width, height = self.plotter.render_window.GetSize()
        x = point.x() * width / max(1, self.plotter.width())
        y = (self.plotter.height() - point.y()) * height / max(1, self.plotter.height()) - 1
        ray = []
        for depth in (0, 1):
            renderer.SetDisplayPoint(x, y, depth)
            renderer.DisplayToWorld()
            value = renderer.GetWorldPoint()
            ray.append(np.asarray(value[:3]) / value[3])
        return ray[0], ray[1] - ray[0]
