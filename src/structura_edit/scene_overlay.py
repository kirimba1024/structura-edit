from itertools import product
from pathlib import Path
from weakref import proxy

import pyvista as pv
from vtkmodules.vtkCommonCore import VTK_FONT_FILE
from vtkmodules.vtkPythonContext2D import vtkPythonItem
from vtkmodules.vtkRenderingContext2D import vtkPen
from vtkmodules.vtkRenderingContextOpenGL2 import vtkOpenGLContextActor

from .appearance import ACCENT, CROSSHAIR, CROSSHAIR_EDGE, FONT_SIZE, GRID, HOVER, PANEL_BACKGROUND, SELECTION, SELECTION_EDGE, SELECTION_WIDTH, SELECTION_FILL, TEMPORARY_FILL, TEXT

class BoundsMarker:
    def __init__(self, plotter, color, *, fill=0, width=1):
        self.plotter = plotter
        self.bounds = None
        box = pv.Box(bounds=(0, 1, 0, 1, 0, 1))
        styles = [("surface", fill)] if fill else []
        if width:
            styles.append(("wireframe", 1))
        self.actors = [plotter.add_mesh(box, style=style, color=color, opacity=opacity, line_width=width or 1,
                                      lighting=False, pickable=False, reset_camera=False, render=False)
                       for style, opacity in styles]
        for actor in self.actors:
            actor.SetVisibility(False)
            actor.SetUseBounds(False)

    def set_bounds(self, bounds):
        if bounds == self.bounds:
            return False
        self.bounds = bounds
        for actor in self.actors:
            actor.SetVisibility(bounds is not None)
            if bounds is not None:
                lower, upper = bounds
                actor.SetPosition(*(v - 0.004 for v in lower))
                actor.SetScale(*(hi - lo + 0.008 for lo, hi in zip(lower, upper)))
        return True


class SceneOverlay:
    def __init__(self, plotter):
        self.plotter = plotter
        self.hover = BoundsMarker(plotter, HOVER)
        self.selection = BoundsMarker(plotter, SELECTION, fill=SELECTION_FILL, width=SELECTION_WIDTH)
        self.temporary = BoundsMarker(plotter, ACCENT, fill=TEMPORARY_FILL, width=0)
        self.looking = False
        self.corners = ()
        self.entity_labels = ()
        self.block_label = ""
        self.hover_label = ""
        self.actor = vtkOpenGLContextActor()
        self.actor.SetPickable(False)
        self.actor.SetUseBounds(False)
        item = vtkPythonItem()
        item.SetPythonObject(proxy(self))
        self.actor.GetScene().AddItem(item)
        plotter.renderer.AddViewProp(self.actor)

    def Initialize(self, item):
        return True

    def set_selection(self, selection, temporary=None, corners=(), *, offset=(0, 0, 0)):
        def shifted(position):
            return tuple(p + d for p, d in zip(position, offset))
        def bounds(region):
            return (shifted(region.lower), shifted(region.upper)) if region else None
        previous = self.corners
        self.corners = tuple(shifted(corner) for corner in corners if corner is not None) if selection else ()
        changed = self.selection.set_bounds(bounds(selection))
        changed |= self.temporary.set_bounds(bounds(temporary))
        if changed or previous != self.corners:
            self.plotter.render()

    def set_block_label(self, label):
        if self.block_label != label:
            self.block_label = label
            self.plotter.render()

    def set_entity_labels(self, labels):
        if self.entity_labels != labels:
            self.entity_labels = labels
            self.plotter.render()

    def set_hover(self, position, *, bounds=None, label=""):
        if position is not None:
            bounds = position, tuple(v + 1 for v in position)
        if bounds == self.selection.bounds or self.temporary.bounds is not None:
            bounds = None
        label = label if bounds is not None else ""
        changed = self.hover.set_bounds(bounds)
        if changed or self.hover_label != label:
            self.hover_label = label
            self.plotter.render()

    def set_looking(self, looking):
        if self.looking != looking:
            self.looking = looking
            self.plotter.render()

    def Paint(self, item, painter):
        scale = self.plotter.render_window.GetDPI() / 72
        self._draw_bounds(painter, scale)
        self._draw_labels(painter, scale)
        if self.looking:
            width, height = self.plotter.render_window.GetSize()
            x, y = width / 2, height / 2
            pen = painter.GetPen()
            pen.SetLineType(vtkPen.SOLID_LINE)
            colors = ((*pv.Color(CROSSHAIR_EDGE).int_rgb, 160), 3), ((*pv.Color(CROSSHAIR).int_rgb, 220), 1)
            for color, width in colors:
                pen.SetColor(*color)
                pen.SetWidth(width * scale)
                for sign in (-1, 1):
                    painter.DrawLine(x + sign * 3 * scale, y, x + sign * 7 * scale, y)
                    painter.DrawLine(x, y + sign * 3 * scale, x, y + sign * 7 * scale)
        return True

    def _draw_bounds(self, painter, scale):
        pen = painter.GetPen()
        pen.SetLineType(vtkPen.DASH_LINE)
        for bounds, alpha in ((self.selection.bounds, 255), (self.temporary.bounds, 200)):
            if bounds is None:
                continue
            points = {}
            for corner in product((0, 1), repeat=3):
                point = self._project(tuple(bounds[c][axis] for axis, c in enumerate(corner)))
                if point is not None:
                    points[corner] = point
            for color, width in ((SELECTION_EDGE, SELECTION_WIDTH + 2), (SELECTION, SELECTION_WIDTH)):
                pen.SetColor(*pv.Color(color).int_rgb, alpha)
                pen.SetWidth(width * scale)
                for corner, point in points.items():
                    for axis in range(3):
                        if corner[axis] == 0:
                            other = tuple(1 if i == axis else value for i, value in enumerate(corner))
                            if other in points:
                                painter.DrawLine(*point, *points[other])

    def _draw_labels(self, painter, scale):
        labels = [(name, tuple(p + 0.5 for p in position)) for name, position in zip("AB", self.corners)]
        if self.corners and self.corners[0] == self.corners[1]:
            labels = [("A/B", tuple(p + 0.5 for p in self.corners[0]))]
        if self.block_label and self.selection.bounds is not None:
            position = tuple(p + 0.5 for p in self.selection.bounds[0])
            labels = [(f"A/B · {self.block_label}" if self.corners else self.block_label, position)]
        labels.extend(self.entity_labels)
        if self.hover_label and self.hover.bounds is not None:
            lower, upper = self.hover.bounds
            position = ((lower[0] + upper[0]) / 2, upper[1] + 0.2, (lower[2] + upper[2]) / 2)
            labels.insert(0, (self.hover_label, position))
        text = painter.GetTextProp()
        text.SetFontFamily(VTK_FONT_FILE)
        text.SetFontFile(str(Path(__file__).parent / "data/fonts/Monocraft.ttf"))
        text.SetFontSize(FONT_SIZE // 2)
        text.SetColor(*pv.Color(TEXT).float_rgb)
        text.SetJustificationToCentered()
        text.SetVerticalJustificationToCentered()
        pen = painter.GetPen()
        pen.SetLineType(vtkPen.SOLID_LINE)
        pen.SetWidth(scale)
        pen.SetColor(*pv.Color(ACCENT).int_rgb)
        painter.GetBrush().SetColor(*pv.Color(PANEL_BACKGROUND).int_rgb)
        occupied = []
        for label, position in labels:
            point = self._project(position)
            if point is None:
                continue
            bounds = [0.0] * 4
            painter.ComputeStringBounds(label, bounds)
            width, height = bounds[2] + GRID * scale, bounds[3] + GRID * scale
            left, bottom = point[0] - width / 2, point[1] - height / 2
            rectangle = left, bottom, left + width, bottom + height
            if any(rectangle[0] < old[2] and rectangle[2] > old[0] and rectangle[1] < old[3] and rectangle[3] > old[1] for old in occupied):
                continue
            occupied.append(rectangle)
            painter.DrawRect(left, bottom, width, height)
            painter.DrawString(*point, label)

    def _project(self, position):
        renderer = self.plotter.renderer
        renderer.SetWorldPoint(*position, 1)
        renderer.WorldToDisplay()
        x, y, depth = renderer.GetDisplayPoint()
        if 0 <= depth <= 1:
            return x, y
        return None
