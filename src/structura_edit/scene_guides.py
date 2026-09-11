from itertools import product
from math import ceil

import numpy as np
import pyvista as pv

from .appearance import CHUNK_LINE_OPACITY, CHUNK_LINE_WIDTH, GUIDE, LOADED_LINE, LOADED_LINE_WIDTH, LOADED_LINE_OPACITY


def box_edges(lower, upper):
    for axis in range(3):
        others = [index for index in range(3) if index != axis]
        for sides in product((0, 1), repeat=2):
            start, end = list(lower), list(lower)
            end[axis] = upper[axis]
            for index, side in zip(others, sides):
                start[index] = end[index] = (lower, upper)[side][index]
            yield tuple(start), tuple(end)


def line_mesh(edges, *, dashed=False):
    points = []
    for first, last in edges:
        first, last = np.asarray(first, dtype=float), np.asarray(last, dtype=float)
        count = min(256, max(1, ceil(np.linalg.norm(last - first) / 2))) if dashed else 1
        for index in range(count):
            start = index / count
            end = (index + (0.5 if dashed else 1)) / count
            points.extend((first + (last - first) * start, first + (last - first) * end))
    if not points:
        return None
    lines = np.column_stack((np.full(len(points) // 2, 2), np.arange(len(points)).reshape(-1, 2)))
    return pv.PolyData(np.asarray(points), lines=lines.ravel())


class SceneGuides:
    def __init__(self, plotter):
        self.plotter = plotter
        self.actors = []
        self.current = None

    def update(self, session, *, bounds=True, chunks=False, sections=False):
        key = (session.size, session.origin, bounds, chunks, sections) if session is not None else None
        if key == self.current:
            return
        self.current = key
        for actor in self.actors:
            self.plotter.remove_actor(actor, reset_camera=False, render=False)
        self.actors.clear()
        if session is None:
            return
        if bounds:
            self._add(line_mesh(box_edges((0, 0, 0), session.size), dashed=True), LOADED_LINE_OPACITY, LOADED_LINE_WIDTH, LOADED_LINE)
        if chunks or sections:
            sx, sy, sz = session.size
            ox, oy, oz = session.origin
            xs = chunk_lines(ox, sx, self.plotter.camera.position[0])
            zs = chunk_lines(oz, sz, self.plotter.camera.position[2])
            ys = sorted({0, sy, *chunk_lines(oy, sy, self.plotter.camera.position[1])}) if sections else (0, sy)
            edges = [((x, y, 0), (x, y, sz)) for x in xs for y in ys]
            edges.extend(((0, y, z), (sx, y, z)) for z in zs for y in ys)
            edges.extend(((x, 0, z), (x, sy, z)) for x in xs for z in zs)
            self._add(line_mesh(edges), CHUNK_LINE_OPACITY, CHUNK_LINE_WIDTH)
        self.plotter.render()

    def _add(self, mesh, opacity, width=1, color=GUIDE):
        if mesh is None:
            return
        actor = self.plotter.add_mesh(mesh, color=color, opacity=opacity, line_width=width,
                                      lighting=False, pickable=False, reset_camera=False, render=False)
        actor.SetUseBounds(False)
        self.actors.append(actor)


def chunk_lines(origin, size, center):
    values = range((-origin) % 16, size + 1, 16)
    start = max(0, min(len(values) - 64, round((center - values.start) / 16) - 32))
    return values[start:start + 64]
