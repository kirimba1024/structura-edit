import os

os.environ["QT_API"] = "pyside6"

from PySide6.QtCore import Qt, Signal
from pyvistaqt import QtInteractor
from vtkmodules.vtkInteractionStyle import vtkInteractorStyleUser

from .appearance import SCENE_BACKGROUND, TEXT

class SceneView(QtInteractor):
    resized = Signal()
    rendered = Signal()

    def __init__(self, parent):
        super().__init__(parent, auto_update=False, multi_samples=0)
        self.set_background(SCENE_BACKGROUND)
        self.enable_depth_peeling(number_of_peels=8)
        self.iren.interactor.SetInteractorStyle(vtkInteractorStyleUser())
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.add_axes(interactive=False, viewport=(0, 0, 0.085, 0.13), line_width=2, color=TEXT,
                      x_color="#e37468", y_color="#8ebd70", z_color="#729bcc")

    def render(self):
        if not self.suppress_rendering:
            super().render()
            self.rendered.emit()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.resized.emit()

    def keyPressEvent(self, event):
        event.accept()

    def keyReleaseEvent(self, event):
        event.accept()
