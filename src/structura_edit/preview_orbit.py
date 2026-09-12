from dataclasses import dataclass
from math import cos, radians, sin
from time import monotonic

from PySide6.QtCore import QEvent, QObject, Qt, QTimer


@dataclass
class Orbit:
    azimuth: float = 35.0
    elevation: float = 29.0

    def advance(self, elapsed):
        self.azimuth = (self.azimuth + 30 * min(.05, max(0, elapsed))) % 360

    def drag(self, dx, dy):
        self.azimuth = (self.azimuth - dx * .5) % 360
        self.elevation = min(80, max(-80, self.elevation + dy * .5))

    def position(self, center, radius):
        azimuth, elevation = radians(self.azimuth), radians(self.elevation)
        x, y, z = center
        return (x + sin(azimuth) * cos(elevation) * radius,
                y + sin(elevation) * radius, z + cos(azimuth) * cos(elevation) * radius)


class PreviewOrbit(QObject):
    def __init__(self, preview, active, update):
        super().__init__(preview)
        self.preview, self.active, self.update = preview, active, update
        self.orientation = Orbit()
        self.previous = monotonic()
        self.pressed = None
        preview.installEventFilter(self)
        preview.setCursor(Qt.CursorShape.OpenHandCursor)
        preview.setToolTip("Drag to rotate the preview")
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self.tick)
        self.timer.start()

    def tick(self):
        now = monotonic()
        elapsed, self.previous = now - self.previous, now
        if self.active() and self.pressed is None and not self.preview.underMouse():
            self.orientation.advance(elapsed)
            self.update()

    def eventFilter(self, watched, event):
        kind = event.type()
        if kind == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            self.pressed = event.position()
            self.preview.setCursor(Qt.CursorShape.ClosedHandCursor)
            return True
        if kind == QEvent.Type.MouseMove and self.pressed is not None:
            delta = event.position() - self.pressed
            self.pressed = event.position()
            self.orientation.drag(delta.x(), delta.y())
            self.update()
            return True
        if kind == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            self.pressed = None
            self.preview.setCursor(Qt.CursorShape.OpenHandCursor)
            return True
        if kind in (QEvent.Type.Hide, QEvent.Type.WindowDeactivate):
            self.pressed = None
        return False

    def close(self):
        self.timer.stop()
