from time import monotonic

from PySide6.QtCore import QEvent, QPointF, QRectF, QSizeF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QApplication, QWidget

from .map_layout import MapLayout, projection_rect
from .map_projection import LABELS, VIEWS, depth_axis, project, unproject
from .appearance import ACCENT, BORDER, MAP_BACKGROUND, PANEL_BACKGROUND, REMOVAL, TEXT


class MapCanvas(QWidget):
    navigate = Signal(object)
    view_changed = Signal()

    def __init__(self):
        super().__init__()
        self.images = {}
        self.tiles = {}
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
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setToolTip("M: expand · Click: enlarge view · Drag / trackpad scroll: pan · Wheel / pinch: zoom · F: camera · Double-click: go here")

    def set_images(self, images):
        self.images = {view: QImage(pixels.data, pixels.shape[1], pixels.shape[0], pixels.strides[0],
                                  QImage.Format.Format_RGBA8888 if pixels.shape[2] == 4 else QImage.Format.Format_RGB888).copy()
                       for view, pixels in images.items()}
        self.update()

    def tile_rect(self, view):
        return self.layout.tile_rect(view)

    def screen_point(self, position, view):
        world = tuple(p + o for p, o in zip(position, self.origin))
        return self.layout.to_screen(QPointF(*project(world, (0, 0, 0), view)), view)

    def image_rect(self, rect, view):
        return QRectF(self.layout.to_screen(rect.topLeft(), view), self.layout.to_screen(rect.bottomRight(), view))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        painter.fillRect(self.rect(), QColor(MAP_BACKGROUND))
        for view, label in zip(VIEWS, LABELS):
            rect = self.tile_rect(view)
            painter.save()
            painter.setClipRect(rect)
            if self.layout.large:
                painter.setOpacity(0.85)
                for (tile_view, x, y), image in self.tiles.items():
                    if tile_view == view:
                        target = self.image_rect(QRectF(x, y, image.width(), image.height()), view)
                        if target.intersects(rect):
                            painter.drawImage(target, image)
                painter.setOpacity(1)
            if view in self.images:
                target = self.image_rect(projection_rect(self.origin, self.size_blocks, view), view)
                painter.drawImage(target, self.images[view])
                if self.layout.large and self.dimension:
                    painter.setPen(QPen(QColor(BORDER), 1, Qt.PenStyle.DashLine))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawRect(target)
            if self.selection is not None:
                lower, upper = self.selection
                selection = QRectF(self.screen_point(lower, view), self.screen_point(upper, view)).normalized()
                painter.setPen(QPen(QColor(ACCENT), 1))
                color = QColor(ACCENT)
                color.setAlpha(22)
                painter.setBrush(color)
                painter.drawRect(selection)
            painter.setPen(QPen(QColor(TEXT), 1))
            for position, player in self.entities:
                painter.setBrush(QColor("#f5f3e8" if player else "#e4ce68"))
                point = self.screen_point(position, view)
                painter.drawRect(QRectF(round(point.x()) - 2, round(point.y()) - 2, 4, 4))
            point = self.screen_point(self.position, view)
            target = self.screen_point(tuple(p + d * 4 for p, d in zip(self.position, self.direction)), view)
            if rect.contains(point):
                direction = target - point
                length = (direction.x() ** 2 + direction.y() ** 2) ** 0.5
                if length > 0.01:
                    direction /= length
                    side = QPointF(-direction.y(), direction.x())
                    painter.setBrush(QColor(REMOVAL))
                    painter.setPen(QPen(QColor("#fff5dc"), 1))
                    painter.drawPolygon(QPolygonF([point + direction * 6, point - direction * 4 + side * 4,
                                                    point - direction * 4 - side * 4]))
                else:
                    painter.setBrush(QColor(REMOVAL))
                    painter.setPen(QPen(QColor("#fff5dc"), 1))
                    painter.drawRect(QRectF(round(point.x()) - 2, round(point.y()) - 2, 4, 4))
            painter.setPen(QPen(QColor(ACCENT if self.layout.large and self.layout.focused == view else BORDER), 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect)
            label = label.upper()
            if rect.width() < 96:
                label = label[:1]
            if self.layout.large and self.dimension and rect.width() > 200:
                axis = depth_axis(view)
                label += f" · {'XYZ'[axis]} {self.origin[axis]}…{self.origin[axis] + self.size_blocks[axis]}"
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
