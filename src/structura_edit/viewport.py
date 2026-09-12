import os

os.environ["QT_API"] = "pyside6"

from PySide6.QtCore import QTimer, Qt, Signal
from pyvistaqt import QtInteractor
from vtkmodules.vtkInteractionStyle import vtkInteractorStyleUser

from .appearance import AXIS_COLORS, SCENE_BACKGROUND, TEXT
from .scene_retirement import SceneRetirement

class SceneView(QtInteractor):
    resized = Signal()

    def __init__(self, parent, *, axes=True):
        super().__init__(parent, auto_update=False, multi_samples=0)
        self.retirement = SceneRetirement(self)
        self.frame_timer = QTimer(self)
        self.frame_timer.setSingleShot(True)
        self.frame_timer.timeout.connect(self._render)
        self.set_background(SCENE_BACKGROUND)
        self.renderer.SetUseDepthPeeling(False)
        self.renderer.SetUseOIT(True)
        self.iren.interactor.SetInteractorStyle(vtkInteractorStyleUser())
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        if axes:
            self.add_axes(interactive=False, viewport=(0, 0.87, 0.085, 1), line_width=2, color=TEXT,
                          x_color=AXIS_COLORS[0], y_color=AXIS_COLORS[1], z_color=AXIS_COLORS[2])

    def render(self):
        if not self.suppress_rendering:
            timer = getattr(self, "frame_timer", None)
            if timer is not None and (not timer.isActive() or timer.remainingTime() > 0):
                timer.start(0)

    def paintEvent(self, event):
        if not self.suppress_rendering and not self.frame_timer.isActive():
            self.frame_timer.start(16)

    def close(self):
        self.retirement.close()
        super().close()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.resized.emit()

    def keyPressEvent(self, event):
        event.accept()

    def keyReleaseEvent(self, event):
        event.accept()
