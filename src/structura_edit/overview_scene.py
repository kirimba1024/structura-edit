from collections import Counter

from itertools import chain

import pyvista as pv

from .overview_model import DETAIL_BUDGET, STAGING_BUDGET
from .scene_geometry import add_geometry_steps, remove_geometry


class OverviewScene:
    def __init__(self, plotter):
        self.plotter = plotter
        self.entries = {}
        self.visible = set()
        self.wanted = set()
        self.textures = {}
        self.texture_users = Counter()
        self.origin = (0, 0, 0)

    def begin(self, wanted):
        self.wanted = set(wanted)
        self._discard_unneeded()

    def missing(self):
        return self.wanted - self.entries.keys()

    def add_steps(self, key, data, nbytes):
        if key in self.entries or key not in self.wanted:
            return
        if sum(entry[2] for entry in self.entries.values()) + nbytes > DETAIL_BUDGET + STAGING_BUDGET:
            raise ValueError("Overview staging exceeds the memory budget")
        texture_keys = []

        def texture_for(mesh):
            identity = mesh.texture_key
            if identity not in self.textures:
                self.textures[identity] = pv.Texture(mesh.image)
            self.texture_users[identity] += 1
            texture_keys.append(identity)
            return self.textures[identity]

        lower = data["origin"]
        actors, complete = [], False
        try:
            for actor in chain(add_geometry_steps(self.plotter, data, texture_factory=texture_for), self._lod_steps(data["colored"])):
                actors.append(actor)
                actor.SetPosition(*(p - o for p, o in zip(lower, self.origin)))
                actor.SetVisibility(False)
                actor.SetPickable(False)
                yield True
            self.entries[key] = actors, texture_keys, nbytes, lower
            complete = True
        finally:
            if not complete:
                remove_geometry(self.plotter, actors)
                self._release_textures(texture_keys)

    def _lod_steps(self, parts):
        for solid, points, faces, colors in parts:
            mesh = pv.PolyData(points, faces)
            mesh.point_data["rgba"] = colors
            actor = self.plotter.add_mesh(mesh, scalars="rgba", rgb=True, ambient=0.35, smooth_shading=False,
                                          reset_camera=False, render=False, show_scalar_bar=False)
            actor.SetForceOpaque(solid)
            yield actor

    def publish(self, origin):
        if self.missing():
            return False
        self.origin = tuple(origin)
        self.visible = self.wanted.copy()
        self._discard_unneeded()
        for key in self.visible:
            lower = self.entries[key][3]
            for actor in self.entries[key][0]:
                actor.SetPosition(*(p - o for p, o in zip(lower, self.origin)))
                actor.SetVisibility(True)
        return True

    def cancel(self):
        self.wanted = self.visible.copy()
        self._discard_unneeded()

    def _release_textures(self, keys):
        for key in keys:
            self.texture_users[key] -= 1
            if not self.texture_users[key]:
                self.texture_users.pop(key)
                self.textures.pop(key, None)

    def _discard_unneeded(self):
        for key in self.entries.keys() - (self.wanted | self.visible):
            actors, textures, _, _ = self.entries.pop(key)
            remove_geometry(self.plotter, actors)
            self._release_textures(textures)

    def clear(self):
        self.wanted.clear()
        self.visible.clear()
        self._discard_unneeded()
