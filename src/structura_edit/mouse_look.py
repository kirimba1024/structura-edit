from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QWidget


class MouseLook:
    def __init__(self, view, *, capture=True):
        self.view = view
        self.capture = capture
        self.active = False
        self.latched = False
        self.anchor = None
        self.restore_position = None
        self.pending = QPoint()

    def start(self, position, *, latched=False):
        if self.active:
            return
        self.pending = QPoint()
        self.restore_position = QCursor.pos() if self.capture else None
        self.anchor = self.view.mapToGlobal(self.view.rect().center()) if self.capture else position
        self.active = True
        self.latched = latched
        if self.capture:
            self.view.setCursor(Qt.CursorShape.BlankCursor)
            self.view.grabMouse()
            QCursor.setPos(self.anchor)

    def move(self, position):
        if self.active and not self.capture:
            self.pending += position - self.anchor
            self.anchor = position

    def sample(self):
        if not self.active:
            return QPoint()
        if self.capture:
            if QWidget.mouseGrabber() is not self.view:
                self.stop(restore=False)
                return QPoint()
            delta = QCursor.pos() - self.anchor
            self.anchor = self.view.mapToGlobal(self.view.rect().center())
            if not delta.isNull() or QCursor.pos() != self.anchor:
                QCursor.setPos(self.anchor)
            return delta
        delta, self.pending = self.pending, QPoint()
        return delta

    def stop(self, *, restore=True):
        active, position = self.active, self.restore_position
        self.active = False
        self.latched = False
        self.anchor = None
        self.restore_position = None
        self.pending = QPoint()
        if active and self.capture:
            if QWidget.mouseGrabber() is self.view:
                self.view.releaseMouse()
            self.view.unsetCursor()
            if restore and position is not None:
                QCursor.setPos(position)
