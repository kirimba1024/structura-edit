from itertools import product

import pyvista as pv
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from .appearance import ACCENT, HOVER, SELECTION_FILL, TEMPORARY_FILL

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


class SceneOverlay(QWidget):
    def __init__(self, plotter):
        super().__init__(plotter)
        self.plotter = plotter
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.hover = BoundsMarker(plotter, HOVER)
        self.selection = BoundsMarker(plotter, ACCENT, fill=SELECTION_FILL, width=2)
        self.temporary = BoundsMarker(plotter, ACCENT, fill=TEMPORARY_FILL, width=0)
        self.looking = False
        plotter.resized.connect(self.reposition)
        plotter.rendered.connect(self.update)
        self.reposition()

    def reposition(self):
        self.setGeometry(self.parentWidget().rect())
        self.update()

    def set_selection(self, selection, temporary=None):
        changed = self.selection.set_bounds((selection.lower, selection.upper) if selection else None)
        changed |= self.temporary.set_bounds((temporary.lower, temporary.upper) if temporary else None)
        if changed:
            self.plotter.render()
            self.update()

    def set_hover(self, position):
        bounds = (position, tuple(v + 1 for v in position)) if position is not None else None
        if bounds == self.selection.bounds or self.temporary.bounds is not None:
            bounds = None
        if self.hover.set_bounds(bounds):
            self.plotter.render()

    def set_looking(self, looking):
        if self.looking != looking:
            self.looking = looking
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        for bounds, alpha in ((self.selection.bounds, 55), (self.temporary.bounds, 220)):
            if bounds is None:
                continue
            points = {}
            renderer = self.plotter.renderer
            width, height = self.plotter.render_window.GetSize()
            for corner in product((0, 1), repeat=3):
                renderer.SetWorldPoint(*(bounds[c][axis] for axis, c in enumerate(corner)), 1)
                renderer.WorldToDisplay()
                x, y, depth = renderer.GetDisplayPoint()
                if 0 <= depth <= 1:
                    points[corner] = QPointF(x * self.width() / max(1, width), self.height() - y * self.height() / max(1, height))
            color = QColor(ACCENT)
            color.setAlpha(alpha)
            painter.setPen(QPen(color, 1, Qt.PenStyle.DashLine))
            for corner, point in points.items():
                for axis in range(3):
                    if corner[axis] == 0:
                        other = tuple(1 if i == axis else value for i, value in enumerate(corner))
                        if other in points:
                            painter.drawLine(point, points[other])
        if self.looking:
            center = QPointF(self.width() / 2, self.height() / 2)
            for color, width in ((QColor(0, 0, 0, 160), 3), (QColor(245, 243, 230, 220), 1)):
                painter.setPen(QPen(color, width))
                for sign in (-1, 1):
                    painter.drawLine(center + QPointF(sign * 3, 0), center + QPointF(sign * 7, 0))
                    painter.drawLine(center + QPointF(0, sign * 3), center + QPointF(0, sign * 7))
