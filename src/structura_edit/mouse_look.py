from PySide6.QtCore import QPointF, QRectF, Qt

from .cocoa_mouse import relative_mouse
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QWidget


class MouseLook:
    def __init__(self, view, *, capture=True):
        self.view = view
        self.capture = capture
        self.relative = relative_mouse(view) if capture else None
        self.active = False
        self.latched = False
        self.anchor = None
        self.restore_position = None
        self.warp_position = None
        self.pending = QPointF()

    def start(self, position, *, latched=False):
        if self.active:
            return
        self.pending = QPointF()
        self.restore_position = QCursor.pos() if self.capture else None
        self.anchor = position
        self.active = True
        self.latched = latched
        if self.capture:
            self.view.setCursor(Qt.CursorShape.BlankCursor)
            self._recenter()
            if self.relative is None or not self.relative.start():
                self.view.grabMouse()

    def move(self, position):
        if self.active and not (self.relative and self.relative.active):
            position = QPointF(position)
            if position == self.warp_position:
                self.anchor = position
                self.warp_position = None
                return
            self.pending += position - self.anchor
            self.anchor = position

    def sample(self):
        if not self.active:
            return QPointF()
        if self.relative is not None and self.relative.active:
            return self.relative.sample()
        if self.capture:
            if QWidget.mouseGrabber() is not self.view:
                self.stop(restore=False)
                return QPointF()
        delta, self.pending = self.pending, QPointF()
        if self.capture and not delta.isNull() and not QRectF(self.view.rect().adjusted(24, 24, -24, -24)).contains(self.anchor):
            self._recenter()
        return delta

    def _recenter(self):
        self.warp_position = self.view.rect().center()
        QCursor.setPos(self.view.mapToGlobal(self.warp_position))
        self.anchor = self.view.mapFromGlobal(QCursor.pos())

    def stop(self, *, restore=True):
        active, position = self.active, self.restore_position
        self.active = False
        self.latched = False
        self.anchor = None
        self.restore_position = None
        self.warp_position = None
        self.pending = QPointF()
        if active and self.capture:
            if self.relative is not None:
                self.relative.stop()
            if QWidget.mouseGrabber() is self.view:
                self.view.releaseMouse()
            self.view.unsetCursor()
            if restore and position is not None:
                QCursor.setPos(position)

    def close(self):
        self.stop()
        if self.relative is not None:
            self.relative.close()
