from time import monotonic

from PySide6.QtCore import QEvent, QPointF, QRectF, QSizeF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QApplication, QWidget

from .map_layout import MapLayout, projection_rect
from .map_entities import MapMarkers, icon_mode
from .loading import MAP_TILE_SIZE
from .overview_store import MAP_SPAN
from .map_projection import LABELS, VIEWS, depth_axis, project, unproject, slice_bounds
from .appearance import ACCENT, BORDER, MAP_BACKGROUND, MAP_CAMERA, MAP_ENTITY, MAP_PLAYER, PANEL_BACKGROUND, REMOVAL, TEXT


class MapCanvas(QWidget):
    navigate = Signal(object)
    view_changed = Signal()
    picked = Signal(str, object, object, bool)

    def __init__(self):
        super().__init__()
        self.images = {}
        self.image_pixels = {}
        self.details = {}
        self.map_cut = None
        self.cave_y = None
        self.tiles = {}
        self.overview = {}
        self.overview_surface = False
        self.height_mode = 'all'
        self.origin = (0, 0, 0)
        self.dimension = None
        self.layout = MapLayout(self)
        self.press = None
        self.dragging = False
        self.focus_time = 0
        self.size_blocks = (1, 1, 1)
        self.position = (0, 0, 0)
        self.direction = (0, 0, -1)
        self.selection = None
        self.entities = []
        self.entity_keys = ()
        self.markers = MapMarkers([])
        self.entity_mode = "Auto"
        self.entity_icons = {}
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setToolTip("M: expand / close · Click a view: enlarge\n"
                       "In enlarged view: click to select · Shift-click to extend\n"
                       "Drag / two fingers: pan · Wheel / pinch: zoom\n"
                       "F: center on camera · Double-click: go here")

    def set_images(self, images):
        self.images = {view: self.images[view] if pixels is self.image_pixels.get(view) and view in self.images else
                      QImage(pixels.data, pixels.shape[1], pixels.shape[0], pixels.strides[0],
                                  QImage.Format.Format_RGBA8888 if pixels.shape[2] == 4 else QImage.Format.Format_RGB888).copy()
                       for view, pixels in images.items()}
        self.image_pixels = images
        self.update()

    def set_entities(self, records, keys=()):
        self.entity_keys = tuple(keys)
        self.entities = [(position, player, label, QImage(pixels.data, pixels.shape[1], pixels.shape[0], pixels.strides[0],
                          QImage.Format.Format_RGBA8888).copy() if pixels is not None else None)
                         for position, player, label, pixels in records]
        self.markers = MapMarkers([record[0] for record in self.entities])
        self.update()

    def marker_rects(self, view, rect):
        if self.entity_mode == "Off" or not self.entities:
            return
        area = self.layout.area(view)
        scale_x, scale_y = rect.width() / max(.001, area.width()), rect.height() / max(.001, area.height())
        pixels = scale_x
        icons = icon_mode(self.entity_mode, pixels, self.entity_icons.get(view, False))
        self.entity_icons[view] = icons
        lower, upper = slice_bounds(self.size_blocks, self.map_cut, view)
        visible = (area.left() - 8 / scale_x, area.top() - 8 / scale_y,
                   area.right() + 8 / scale_x, area.bottom() + 8 / scale_y)
        indices, points = self.markers.visible(view, self.origin, visible, (lower, upper), self.cave_y)
        for index, (u, v) in zip(indices, points):
            _, player, _, icon = self.entities[index]
            point = QPointF(rect.left() + (u - area.left()) * scale_x, rect.top() + (v - area.top()) * scale_y)
            if icons and icon is not None:
                target = QRectF(round(point.x()) - 8, round(point.y()) - 8, 16, 16)
            else:
                target = QRectF(round(point.x()) - 2, round(point.y()) - 2, 4, 4)
            yield index, target, icons and icon is not None

    def draw_entities(self, painter, view, rect):
        painter.setPen(QPen(QColor(TEXT), 1))
        for index, target, icons in self.marker_rects(view, rect):
            _, player, _, icon = self.entities[index]
            if icons:
                painter.fillRect(target, QColor(PANEL_BACKGROUND))
                painter.drawImage(target, icon)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(target)
            else:
                painter.setBrush(QColor(MAP_PLAYER if player else MAP_ENTITY))
                painter.drawRect(target)

    def pick(self, view, point, extend=False):
        entity = next((self.entity_keys[index] for index, rect, _ in reversed(list(self.marker_rects(view, self.tile_rect(view))))
                       if rect.contains(point) and index < len(self.entity_keys)), None)
        projected = self.layout.from_screen(point, view)
        world = tuple(p + o for p, o in zip(self.position, self.origin))
        target = unproject((projected.x(), projected.y()), world, (0, 0, 0), view)
        self.picked.emit(view, tuple(p - o for p, o in zip(target, self.origin)), entity, extend)

    def tile_rect(self, view):
        return self.layout.tile_rect(view)

    def set_details(self, details):
        self.details = {view: (area, QImage(pixels.data, pixels.shape[1], pixels.shape[0], pixels.strides[0],
                                          QImage.Format.Format_RGB888).copy())
                        for view, (area, pixels) in details.items()}
        self.update()

    def screen_point(self, position, view, transform=None):
        world = tuple(p + o for p, o in zip(position, self.origin))
        point = QPointF(*project(world, (0, 0, 0), view))
        return (transform or self.layout.transform(view)).map(point)

    def image_rect(self, rect, view, transform=None):
        return (transform or self.layout.transform(view)).mapRect(rect)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        painter.fillRect(self.rect(), QColor(MAP_BACKGROUND))
        for view, label in zip(VIEWS, LABELS):
            rect = self.tile_rect(view)
            transform = self.layout.transform(view)
            painter.save()
            painter.setClipRect(rect)
            if self.dimension:
                painter.fillRect(rect, QBrush(QColor(BORDER), Qt.BrushStyle.BDiagPattern))
            if view == "top" and self.map_cut is None and self.height_mode == 'all' and self.overview_surface:
                for (level, x, z), image in self.overview.items():
                    span = MAP_SPAN * 2**level
                    target = transform.mapRect(QRectF(x * span, z * span, span, span))
                    if target.intersects(rect):
                        painter.drawImage(target, image)
            if self.layout.large:
                for (tile_view, x, y), image in self.tiles.items():
                    if tile_view == view:
                        target = self.image_rect(QRectF(x, y, MAP_TILE_SIZE, MAP_TILE_SIZE), view, transform)
                        if target.intersects(rect):
                            painter.drawImage(target, image)
            if view in self.images:
                target = self.image_rect(projection_rect(self.origin, self.size_blocks, view), view, transform)
                painter.drawImage(target, self.images[view])
                if self.layout.large and self.dimension:
                    painter.setPen(QPen(QColor(BORDER), 1, Qt.PenStyle.DashLine))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawRect(target)
            if self.layout.large and view in self.details:
                area, image = self.details[view]
                x0, y0, x1, y1 = area
                source = projection_rect(self.origin, self.size_blocks, view)
                target = self.image_rect(QRectF(source.left() + x0, source.top() + y0, x1 - x0, y1 - y0), view, transform)
                painter.drawImage(target, image)
            if self.selection is not None:
                lower, upper = self.selection
                selection = QRectF(self.screen_point(lower, view, transform), self.screen_point(upper, view, transform)).normalized()
                painter.setPen(QPen(QColor(ACCENT), 1))
                color = QColor(ACCENT)
                color.setAlpha(22)
                painter.setBrush(color)
                painter.drawRect(selection)
            self.draw_entities(painter, view, rect)
            point = self.screen_point(self.position, view, transform)
            target = self.screen_point(tuple(p + d * 4 for p, d in zip(self.position, self.direction)), view, transform)
            if rect.contains(point):
                direction = target - point
                length = (direction.x() ** 2 + direction.y() ** 2) ** 0.5
                if length > 0.01:
                    direction /= length
                    side = QPointF(-direction.y(), direction.x())
                    painter.setBrush(QColor(REMOVAL))
                    painter.setPen(QPen(QColor(MAP_CAMERA), 1))
                    painter.drawPolygon(QPolygonF([point + direction * 6, point - direction * 4 + side * 4,
                                                    point - direction * 4 - side * 4]))
                else:
                    painter.setBrush(QColor(REMOVAL))
                    painter.setPen(QPen(QColor(MAP_CAMERA), 1))
                    painter.drawRect(QRectF(round(point.x()) - 2, round(point.y()) - 2, 4, 4))
            painter.setPen(QPen(QColor(ACCENT if self.layout.large and self.layout.focused == view else BORDER), 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect)
            if view == "bottom" and self.cave_y is not None:
                label = f"Cave · Y {self.origin[1] + self.cave_y}"
            label = label.upper()
            if rect.width() < 96:
                label = label[:1]
            if self.layout.large and self.map_cut is not None and rect.width() > 200 and view != "bottom":
                axis = depth_axis(view)
                label += f" · {'XYZ'[axis]} {self.origin[axis] + self.map_cut[axis]}"
            label_rect = QRectF(rect.topLeft() + QPointF(3, 2), QSizeF(painter.fontMetrics().size(0, label)))
            painter.fillRect(label_rect.adjusted(-2, -1, 2, 1), QColor(PANEL_BACKGROUND))
            painter.setPen(QColor(TEXT))
            painter.drawText(label_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, label)
            painter.restore()
        painter.setPen(QPen(QColor(BORDER), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

    def mouseDoubleClickEvent(self, event):
        self.press = None
        if self.layout.large and monotonic() - self.focus_time < QApplication.doubleClickInterval() / 1000:
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            for view in VIEWS:
                rect = self.tile_rect(view)
                if view not in self.images or not rect.contains(event.position()):
                    continue
                point = self.layout.from_screen(event.position(), view)
                world = tuple(p + o for p, o in zip(self.position, self.origin))
                target = unproject((point.x(), point.y()), world, (0, 0, 0), view)
                self.navigate.emit(tuple(p - o for p, o in zip(target, self.origin)))
                event.accept()
                return
        event.accept()

    def mousePressEvent(self, event):
        if self.layout.large and event.button() == Qt.MouseButton.LeftButton:
            view = self.view_at(event.position())
            self.press = (view, event.position(), event.position()) if view is not None else None
            self.dragging = False
        event.accept()

    def mouseMoveEvent(self, event):
        if self.press is not None:
            view, start, previous = self.press
            self.dragging |= (event.position() - start).manhattanLength() >= QApplication.startDragDistance()
            if self.dragging and self.layout.focused in (None, view):
                self.layout.pan(view, event.position() - previous)
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                self.view_changed.emit()
                self.update()
            self.press = view, start, event.position()
        event.accept()

    def mouseReleaseEvent(self, event):
        if self.press is not None and event.button() == Qt.MouseButton.LeftButton:
            view, _, _ = self.press
            if not self.dragging and view != self.layout.focused:
                self.layout.focused = view
                self.focus_time = monotonic()
                self.view_changed.emit()
                self.update()
            elif not self.dragging:
                self.pick(view, event.position(), bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier))
            self.press = None
            self.unsetCursor()
        event.accept()

    def wheelEvent(self, event):
        if self.layout.large:
            view = self.view_at(event.position())
            if view is not None and self.layout.focused in (None, view):
                if not event.pixelDelta().isNull():
                    self.layout.pan(view, QPointF(event.pixelDelta()))
                else:
                    self.layout.zoom_at(view, event.position(), 1.2 ** (event.angleDelta().y() / 120))
                self.view_changed.emit()
                self.update()
        event.accept()

    def event(self, event):
        if event.type() == QEvent.Type.NativeGesture:
            if self.layout.large and event.gestureType() == Qt.NativeGestureType.ZoomNativeGesture:
                view = self.view_at(event.position())
                if view is not None and self.layout.focused in (None, view):
                    self.layout.zoom_at(view, event.position(), max(0.01, 1 + event.value()))
                    self.view_changed.emit()
                    self.update()
            event.accept()
            return True
        return super().event(event)

    def view_at(self, point):
        return next((view for view in VIEWS if self.tile_rect(view).contains(point)), None)
