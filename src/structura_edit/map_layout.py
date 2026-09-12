from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QTransform

from .map_projection import VIEWS, plane_size, project
from .appearance import MAP_ICON_SIZE
from .loading import MAP_TILE_SIZE, MAX_MAP_VISIBLE_TILES


COMPACT_SPAN = 64


def projection_rect(origin, size, view):
    first = project(origin, (0, 0, 0), view)
    last = project(tuple(p + s for p, s in zip(origin, size)), (0, 0, 0), view)
    return QRectF(QPointF(*first), QPointF(*last)).normalized()


class MapLayout:
    def __init__(self, canvas):
        self.canvas = canvas
        self.large = False
        self.focused = None
        self.centers = {}
        self.panned = set()
        self.zoom = dict.fromkeys(VIEWS, 1.0)
        self.framed_size = (1, 1, 1)

    def reset(self):
        self.framed_size = self.canvas.size_blocks
        self.centers = {view: projection_rect(self.canvas.origin, self.framed_size, view).center() for view in VIEWS}
        self.zoom = dict.fromkeys(VIEWS, 1.0)
        self.focused = None
        self.panned.clear()

    def tile_rect(self, view):
        width, height = self.canvas.width(), self.canvas.height()
        if not self.large:
            return QRectF(0, 0, width, height) if view == "top" else QRectF()
        if self.large and self.focused:
            strip = min(MAP_ICON_SIZE, height // 5, width // 5)
            if view == self.focused:
                return QRectF(0, 0, width, height - strip)
            index = [v for v in VIEWS if v != self.focused].index(view)
            left = (width - strip * 5) // 2 + index * strip
            return QRectF(left, height - strip, strip, strip)
        index = VIEWS.index(view)
        column, row = index % 3, index // 3
        left, right = column * width // 3, (column + 1) * width // 3
        top, bottom = row * height // 2, (row + 1) * height // 2
        return QRectF(left, top, right - left, bottom - top)

    def area(self, view):
        source = projection_rect(self.canvas.origin, self.canvas.size_blocks, view)
        tile = self.tile_rect(view)
        if tile.isEmpty():
            return QRectF()
        if not self.large or self.focused is not None and self.focused != view:
            width, height = plane_size(self.framed_size, view)
            width, height = min(width, COMPACT_SPAN), min(height, COMPACT_SPAN)
            scale = min(tile.width() / width, tile.height() / height)
            center = self.camera_center(view)
        else:
            width, height = plane_size(self.framed_size, view)
            quota = MAX_MAP_VISIBLE_TILES if self.focused == view else MAX_MAP_VISIBLE_TILES // len(VIEWS)
            span = (int(quota ** 0.5) - 1) * MAP_TILE_SIZE
            scale = max(max(tile.width(), tile.height()) / span,
                        min(tile.width() / width, tile.height() / height) * self.zoom[view])
            center = self.centers.get(view, source.center()) if view in self.panned else self.camera_center(view)
        width, height = tile.width() / scale, tile.height() / scale
        return QRectF(center.x() - width / 2, center.y() - height / 2, width, height)

    def camera_center(self, view):
        position = tuple(p + o for p, o in zip(self.canvas.position, self.canvas.origin))
        return QPointF(*project(position, (0, 0, 0), view))

    def to_screen(self, point, view):
        return self.transform(view).map(point)

    def transform(self, view):
        tile, area = self.tile_rect(view), self.area(view)
        sx, sy = tile.width() / area.width(), tile.height() / area.height()
        return QTransform(sx, 0, 0, sy, tile.left() - area.left() * sx, tile.top() - area.top() * sy)

    def from_screen(self, point, view):
        tile, area = self.tile_rect(view), self.area(view)
        return QPointF(area.left() + (point.x() - tile.left()) * area.width() / tile.width(),
                       area.top() + (point.y() - tile.top()) * area.height() / tile.height())

    def pan(self, view, delta):
        tile, area = self.tile_rect(view), self.area(view)
        self.centers[view] = area.center() - QPointF(delta.x() * area.width() / tile.width(),
                                                   delta.y() * area.height() / tile.height())
        self.panned.add(view)

    def zoom_at(self, view, point, factor):
        before = self.from_screen(point, view)
        self.centers[view] = self.area(view).center()
        self.panned.add(view)
        self.zoom[view] = min(64, max(0.125, self.zoom[view] * factor))
        self.centers[view] = self.area(view).center() + before - self.from_screen(point, view)

    def recenter(self):
        self.panned.clear()
        self.centers = {view: self.camera_center(view) for view in VIEWS}
