from concurrent.futures import ThreadPoolExecutor
from collections import OrderedDict
from math import floor, log2
from time import monotonic

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from .overview_model import SETTLE_MILLISECONDS
from .overview_store import MAP_SPAN
from .map_image_cache import MapImageCache


class WorldMap(QWidget):
    navigate = Signal(object)
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.snapshot = None
        self.images = {}
        self.view_states = OrderedDict()
        self.base = {}
        self.center = (0.0, 0.0)
        self.scale = 1.0
        self.position = (0, 0, 0)
        self.direction = (0, 0, 1)
        self.follow = True
        self.press = None
        self.target = None
        self.loaded = None
        self.future = None
        self.deadline = 0.0
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="overview-map")
        self.cache = MapImageCache()
        self.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents)
        self.setMouseTracking(True)

    def _images(self, arrays):
        return {key: QImage(array.data, array.shape[1], array.shape[0], array.strides[0], QImage.Format.Format_RGBA8888).copy()
                for key, array in arrays.items()}

    def set_snapshot(self, snapshot):
        def identity(value):
            data = value["metadata"]
            return data["world"], data["dimension"], data["height"]["mode"], data["height"]["y"], data["below_y"]

        if self.snapshot is not None:
            self.view_states[identity(self.snapshot)] = self.center, self.scale, self.follow
            while len(self.view_states) > 16:
                self.view_states.popitem(last=False)
        self.snapshot = snapshot
        self.target = self.loaded = None
        self.images.clear()
        self.base = self._images(snapshot["maps"]) if snapshot else {}
        if snapshot:
            key = identity(snapshot)
            if key in self.view_states:
                self.center, self.scale, self.follow = self.view_states[key]
                self.request()
            else:
                self.fit()
        self.update()

    def set_camera(self, position, direction):
        self.position, self.direction = tuple(position), tuple(direction)
        if self.follow:
            self.center = position[0], position[2]
            self.request()
        self.update()

    def recenter(self):
        self.follow = True
        self.set_camera(self.position, self.direction)

    def fit(self):
        if not self.snapshot:
            return
        lower, upper = self.snapshot["metadata"]["bounds"]
        self.center = tuple((lower[axis] + upper[axis]) / 2 for axis in (0, 2))
        self.scale = min(max(1, self.width() - 32) / max(1, upper[0] - lower[0]),
                         max(1, self.height() - 32) / max(1, upper[2] - lower[2]))
        self.follow = False
        self.request()
        self.update()

    def world_at(self, point):
        return (self.center[0] + (point.x() - self.width() / 2) / self.scale,
                self.center[1] + (point.y() - self.height() / 2) / self.scale)

    def screen_at(self, position):
        return QPointF((position[0] - self.center[0]) * self.scale + self.width() / 2,
                       (position[1] - self.center[1]) * self.scale + self.height() / 2)

    def zoom_at(self, point, factor):
        before = self.world_at(point)
        maximum = self.snapshot["metadata"]["map_level"] if self.snapshot else 8
        self.scale = min(32.0, max(2.0**(-maximum - 2), self.scale * factor))
        after = self.world_at(point)
        self.center = tuple(c + a - b for c, a, b in zip(self.center, before, after))
        self.follow = False
        self.request()
        self.update()

    def request(self):
        if self.snapshot is None:
            return
        level = min(self.snapshot["metadata"]["map_level"], max(0, floor(log2(1 / self.scale))))
        lower = self.world_at(QPointF(0, 0))
        upper = self.world_at(QPointF(self.width(), self.height()))
        bounds = self.snapshot["metadata"]["bounds"]
        lower = tuple(max(value, bounds[0][axis]) for value, axis in zip(lower, (0, 2)))
        upper = tuple(min(value, bounds[1][axis]) for value, axis in zip(upper, (0, 2)))
        while True:
            span = MAP_SPAN * 2**level
            ranges = tuple(range(floor(lo / span), floor(hi / span) + 1) for lo, hi in zip(lower, upper))
            if len(ranges[0]) * len(ranges[1]) <= 192 or level == self.snapshot["metadata"]["map_level"]:
                break
            level += 1
        keys = tuple((level, x, z) for x in ranges[0] for z in ranges[1])
        target = self.snapshot["path"], keys
        if target != self.target:
            self.target = target
            self.deadline = monotonic() + SETTLE_MILLISECONDS / 1000

    def tick(self):
        if self.future is not None and self.future[1].done():
            target, future = self.future
            self.future = None
            try:
                images = future.result()
                if target == self.target:
                    self.images = images
                    self.loaded = target
                    self.update()
            except Exception as error:
                if target == self.target:
                    self.loaded = target
                    self.failed.emit(str(error))
        if self.snapshot and self.isVisible() and self.future is None and self.target != self.loaded and monotonic() >= self.deadline:
            self.future = self.target, self.executor.submit(self.cache.read, *self.target)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#141b24"))
        painter.setPen(QPen(QColor("#27313b"), 1))
        for offset in range(-self.height(), self.width(), 20):
            painter.drawLine(offset, self.height(), offset + self.height(), 0)
        for collection in (self.base, self.images):
            for (level, x, z), image in collection.items():
                span = MAP_SPAN * 2**level
                rect = QRectF(self.screen_at((x * span, z * span)), self.screen_at(((x + 1) * span, (z + 1) * span)))
                if rect.intersects(QRectF(self.rect())):
                    painter.drawImage(rect, image)
        point = self.screen_at((self.position[0], self.position[2]))
        direction = QPointF(self.direction[0], self.direction[2])
        length = max(0.001, (direction.x()**2 + direction.y()**2)**0.5)
        direction /= length
        right = QPointF(-direction.y(), direction.x())
        painter.setPen(QPen(QColor("#101820"), 2))
        painter.setBrush(QColor("#f5da70"))
        painter.drawPolygon(QPolygonF([point + direction * 9, point - direction * 5 + right * 5,
                                     point - direction * 5 - right * 5]))
        if self.snapshot:
            metadata = self.snapshot["metadata"]
            layer = f" · Below {metadata['below_y']}" if metadata["below_y"] is not None else " · Surface"
            if metadata["height"]["mode"] != "all":
                layer = f" · {metadata['height']['mode'].capitalize()} {metadata['height']['y']}"
            painter.setPen(QColor("#edf1f4"))
            painter.drawText(self.rect().adjusted(8, 8, -8, -8), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
                             metadata["dimension"].split(":")[-1] + layer)

    def resizeEvent(self, event):
        self.request()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.press = event.position(), self.center
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if self.press is not None:
            point, center = self.press
            delta = event.position() - point
            self.center = center[0] - delta.x() / self.scale, center[1] - delta.y() / self.scale
            self.follow = False
            self.request()
            self.update()

    def mouseReleaseEvent(self, event):
        self.press = None
        self.unsetCursor()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.navigate.emit(tuple(floor(value) for value in self.world_at(event.position())))

    def wheelEvent(self, event):
        delta = event.pixelDelta()
        if not delta.isNull():
            self.center = self.center[0] - delta.x() / self.scale, self.center[1] - delta.y() / self.scale
            self.follow = False
            self.request()
            self.update()
        else:
            self.zoom_at(event.position(), 1.2**(event.angleDelta().y() / 120))
        event.accept()

    def event(self, event):
        if event.type() == QEvent.Type.NativeGesture and event.gestureType() == Qt.NativeGestureType.ZoomNativeGesture:
            self.zoom_at(event.position(), max(0.1, 1 + event.value()))
            return True
        return super().event(event)

    def shutdown(self):
        self.target = None
        self.executor.shutdown(wait=False, cancel_futures=True)
