import numpy as np
import pyvista as pv

from .picking import pick_block
from .loading import replacement_sizes
from .appearance import GHOST_OPACITY, REMOVAL, REMOVAL_OPACITY
from .scene_geometry import add_geometry
from .height_slice import HeightSlice


class Scene:
    def __init__(self, plotter):
        self.plotter = plotter
        self.sections = {}
        self.section_bytes = {}
        self.signatures = {}
        self.ghost_actors = {}
        self.removed_bytes = {}
        self.display_revision = None
        self.entity_bounds = {}
        self.entity_keys = ()
        self.entity_markers = []
        self.entity_boxes = np.empty((0, 2, 3))
        self.height = HeightSlice()

    @property
    def actors(self):
        return [actor for actors in self.sections.values() for actor in actors]

    def clear(self):
        self._remove(self.actors)
        self.sections.clear()
        self.section_bytes.clear()
        self.signatures.clear()
        self.removed_bytes.clear()
        self.display_revision = None
        self.entity_bounds = {}
        self.entity_keys = ()
        self.entity_markers = []
        self.entity_boxes = np.empty((0, 2, 3))

    def replace(self, data, revision):
        for _ in self.replace_steps(data, revision):
            pass

    def replace_steps(self, data, revision):
        sizes = replacement_sizes(data, self.section_bytes)
        replacements = {}
        reused = set()
        committed = False
        try:
            for key, section in data["sections"].items():
                if section.get("signature") is not None and self.signatures.get(key) == section["signature"] and key in self.sections:
                    reused.add(key)
                    continue
                replacements[key] = self._add_section(section)
                for actor in replacements[key]:
                    actor.SetVisibility(False)
                yield True
            if data["reset"]:
                self._remove(actor for key, actors in self.sections.items() if key not in reused for actor in actors)
                self.sections = {key: self.sections[key] for key in reused}
                self.signatures = {key: self.signatures[key] for key in reused}
                self.removed_bytes.clear()
            else:
                for key in replacements:
                    self._remove(self.sections.get(key, []))
            for section in data["sections"].values():
                if "entity_bounds" in section:
                    self.entity_bounds = section["entity_bounds"]
                    self.entity_keys = tuple(self.entity_bounds)
                    self.entity_boxes = np.asarray(list(self.entity_bounds.values()))
                    self.entity_markers = section.get("entity_markers", [])
            self.sections.update(replacements)
            self.signatures.update((key, section.get("signature")) for key, section in data["sections"].items())
            self.removed_bytes.update((key, section.get("layers", {}).get("removed", {}).get("geometry_bytes", 0))
                                      for key, section in data["sections"].items())
            self.section_bytes = sizes
            self.display_revision = revision
            for actors in replacements.values():
                for actor in actors:
                    actor.SetVisibility(True)
            committed = True
        finally:
            if not committed:
                self._remove(actor for actors in replacements.values() for actor in actors)

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
        self.signatures.clear()
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
        return pick_block(session, *self.ray_at(point), height=self.height)

    def entity_at(self, session, point):
        from .entity_picking import nearest_entity

        ray = self.ray_at(point)
        return nearest_entity(self.entity_keys, self.entity_boxes, *ray, block=pick_block(session, *ray, height=self.height))

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
