from pathlib import Path
from weakref import proxy

import numpy as np
import pyvista as pv
from vtkmodules.vtkCommonCore import VTK_FONT_FILE
from vtkmodules.vtkPythonContext2D import vtkPythonItem
from vtkmodules.vtkRenderingContext2D import vtkPen
from vtkmodules.vtkRenderingContextOpenGL2 import vtkOpenGLContextActor

from .appearance import AXIS_COLORS, FONT_SIZE, PANEL_BACKGROUND, TEXT


class AxisGizmo:
    LENGTH = 80
    HIT_RADIUS = 12

    def __init__(self, plotter, visible):
        self.plotter, self.visible = plotter, visible
        self.position = None
        self.active_axis = None
        self.actor = vtkOpenGLContextActor()
        self.actor.SetPickable(False)
        self.actor.SetUseBounds(False)
        item = vtkPythonItem()
        item.SetPythonObject(proxy(self))
        self.actor.GetScene().AddItem(item)
        plotter.renderer.AddViewProp(self.actor)

    def Initialize(self, item):
        return True

    def project(self, position):
        renderer = self.plotter.renderer
        renderer.SetWorldPoint(*position, 1)
        renderer.WorldToDisplay()
        x, y, depth = renderer.GetDisplayPoint()
        if not 0 <= depth <= 1:
            return None
        width, height = self.plotter.render_window.GetSize()
        return np.array((x * self.plotter.width() / max(1, width),
                         self.plotter.height() - y * self.plotter.height() / max(1, height)))

    def handles(self):
        if self.position is None or not self.visible():
            return {}
        start = self.project(self.position)
        if start is None:
            return {}
        result = {}
        direction = self.plotter.camera.direction
        for axis in range(3):
            if 1 - direction[axis] ** 2 < 0.04:
                continue
            point = np.asarray(self.position, dtype=float).copy()
            point[axis] += 1
            end = self.project(point)
            if end is not None and np.linalg.norm(end - start) > 1e-6:
                result[axis] = start, start + (end - start) * self.LENGTH / np.linalg.norm(end - start)
        return result

    def hit(self, point):
        point = np.array((point.x(), point.y()))
        candidates = []
        for axis, (start, end) in self.handles().items():
            vector = end - start
            fraction = float((point - start) @ vector) / (self.LENGTH ** 2)
            if 0.2 <= fraction <= 1.15:
                distance = np.linalg.norm(point - (start + np.clip(fraction, 0, 1) * vector))
                if distance <= self.HIT_RADIUS:
                    candidates.append((distance, axis))
        return min(candidates)[1] if candidates else None

    def Paint(self, item, painter):
        width, height = self.plotter.render_window.GetSize()
        scale = width / max(1, self.plotter.width())
        pen = painter.GetPen()
        pen.SetLineType(vtkPen.SOLID_LINE)
        text = painter.GetTextProp()
        text.SetFontFamily(VTK_FONT_FILE)
        text.SetFontFile(str(Path(__file__).parent / "data/fonts/Monocraft.ttf"))
        text.SetFontSize(FONT_SIZE // 2)
        text.SetJustificationToCentered()
        text.SetVerticalJustificationToCentered()
        text.SetColor(*pv.Color(TEXT).float_rgb)
        for axis, (start, end) in self.handles().items():
            start, end = (np.array((point[0] * scale, height - point[1] * scale)) for point in (start, end))
            pen.SetColor(*pv.Color(AXIS_COLORS[axis]).int_rgb)
            pen.SetWidth((4 if axis == self.active_axis else 2) * scale)
            painter.DrawLine(*start, *end)
            painter.GetBrush().SetColor(*pv.Color(PANEL_BACKGROUND).int_rgb)
            painter.DrawRect(*(end - 10 * scale), 20 * scale, 20 * scale)
            painter.DrawString(*end, "XYZ"[axis])
        return True
