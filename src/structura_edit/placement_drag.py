from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QApplication

from .axis_drag import AxisDrag
from .axis_gizmo import AxisGizmo


class PlacementDrag(QObject):
    def __init__(self, placement):
        super().__init__(placement)
        self.placement = placement
        self.scene = placement.scene
        self.view = self.scene.plotter
        self.drag = None
        self.gizmo = AxisGizmo(self.view, self.available)
        QApplication.instance().installEventFilter(self)

    def available(self):
        placement = self.placement
        return (placement.model is not None and not placement.model.following and placement.visible
                and placement.review is None and placement.scene_ready and not placement.busy
                and placement.navigation.enabled and not placement.navigation.looking)

    def refresh(self):
        model = self.placement.model
        self.gizmo.position = tuple(p + a + 0.5 for p, a in zip(model.position, model.anchor)) if model else None
        if self.drag is not None and not self.available():
            self.finish()

    def finish(self, *, cancel=False):
        drag, self.drag = self.drag, None
        self.gizmo.active_axis = None
        if cancel and drag is not None:
            self.placement.set_position(drag.position)
        self.view.render()

    def eventFilter(self, watched, event):
        kind = event.type()
        if self.drag is not None and (kind == QEvent.Type.ApplicationDeactivate or
                (watched is self.view and kind in (QEvent.Type.FocusOut, QEvent.Type.Hide)) or
                (watched is self.view.window() and kind in (QEvent.Type.WindowDeactivate, QEvent.Type.WindowBlocked))):
            self.finish()
        if watched is not self.view:
            return False
        if self.drag is not None:
            if kind in (QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
                if kind == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
                    self.finish(cancel=True)
                return True
            if kind == QEvent.Type.MouseMove:
                if not event.buttons() & Qt.MouseButton.LeftButton:
                    self.finish()
                else:
                    position = self.drag.moved(self.scene.ray_at(event.position().toPoint()))
                    if position is not None:
                        self.placement.set_position(position)
                return True
            if kind == QEvent.Type.MouseButtonRelease:
                if event.button() == Qt.MouseButton.LeftButton:
                    self.finish()
                return True
            if kind in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick, QEvent.Type.Wheel):
                return True
        if self.available() and kind == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            point = event.position().toPoint()
            axis = self.gizmo.hit(point)
            if axis is not None:
                drag = AxisDrag.begin(self.placement.model.position, self.gizmo.position, axis,
                                      self.view.camera.direction, self.scene.ray_at(point))
                if drag is not None:
                    self.placement.navigation.stop()
                    self.view.setFocus()
                    self.drag = drag
                    self.gizmo.active_axis = axis
                    self.view.render()
                    return True
        return False
