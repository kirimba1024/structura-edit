from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QApplication, QInputDialog

from .paint import MAX_STROKE_POINTS


class PaintController(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.active = False
        self.points = None
        self.radius = 1
        self.token = None
        window.navigation.hovered.connect(self.hover)
        QApplication.instance().installEventFilter(self)

    @property
    def dragging(self):
        return self.points is not None

    def toggle(self):
        window = self.window
        if self.active:
            if window.tasks.kind == "paint":
                window.cancel_task()
            window.edits.invalidate("paint")
        if not self.active:
            if window.document.selected.current is None:
                return
            window.navigation.stop()
            radius, accepted = QInputDialog.getInt(window, "Paint selected blocks", "Radius (blocks):", self.radius, 1, 16)
            if not accepted:
                window.menus.actions["paint"].setChecked(False)
                return
            self.radius = radius
            window.operation.mode.setCurrentText("Fill")
            window.connected.set_active(False)
            if window.planar.active:
                window.planar.toggle()
        self.cancel()
        self.active = not self.active
        window.menus.actions["paint"].setChecked(self.active)
        window.status.setText("Paint: drag over selected blocks · release to preview · Enter applies · Esc cancels" if self.active else "Paint off")

    def cancel(self):
        self.points = None

    def hover(self, point):
        if self.dragging and self.window.navigation.looking and point is not None:
            self.sample(point)

    def sample(self, point):
        if self.window.navigation.looking:
            point = self.window.plotter.rect().center()
        hit = self.window.scene.hit_at(self.window.document.session, point)
        sample = tuple(value + 0.5 for value in hit.position) if hit is not None else None
        if not self.points or sample != self.points[-1]:
            self.points.append(sample)
        if len(self.points) > MAX_STROKE_POINTS:
            self.cancel()
            self.window.status.setText("Stroke cancelled: more than 4096 samples")

    def finish(self):
        window = self.window
        points, self.points = self.points, None
        if not points or self.token != window.document.input_token:
            return
        values = window.operation.values()
        target = values.get("target", window.operation.fields["target"].text())
        if window.edits.prepare("paint", points=tuple(points), target=target, radius=self.radius, condition=values.get("mask")):
            window.panels.show("operation", focus=False)

    def eventFilter(self, watched, event):
        if not self.active:
            return False
        window = self.window
        if window.placement.active or window.repeat.active or window.planar.active or window.connected.active:
            self.cancel()
            self.active = False
            window.menus.actions["paint"].setChecked(False)
            return False
        kind = event.type()
        if watched is window.plotter and kind == QEvent.Type.Leave and self.dragging:
            if not self.points or self.points[-1] is not None:
                self.points.append(None)
        if kind == QEvent.Type.ApplicationDeactivate or (watched is window and kind == QEvent.Type.WindowDeactivate) or (
                watched is window.plotter and kind in (QEvent.Type.FocusOut, QEvent.Type.Hide)):
            if self.dragging:
                self.cancel()
                window._sync()
        if kind == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape and self.dragging:
            self.cancel()
            window.status.setText("Stroke cancelled")
            window._sync()
            return True
        if kind == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton and self.dragging:
            if watched is window.plotter and window.plotter.rect().contains(event.position().toPoint()):
                self.sample(event.position().toPoint())
                self.finish()
            else:
                self.cancel()
                window.status.setText("Stroke cancelled outside the viewport")
            window._sync()
            return True
        if watched is not window.plotter or window.tasks.busy or window.document.pending is not None:
            return False
        if kind == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            self.token = window.document.input_token
            self.points = []
            self.sample(event.position().toPoint())
            window._sync()
            return True
        if kind == QEvent.Type.MouseMove and self.dragging:
            if window.navigation.looking:
                return False
            self.sample(event.position().toPoint())
            return True
        return False

    def close(self):
        self.cancel()
        QApplication.instance().removeEventFilter(self)
