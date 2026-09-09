import pyvista as pv
from PySide6.QtCore import QObject, Signal

from .changes_view import summary
from .scene_lines import box_outlines


ACCENT_OUTLINE = "#26a888"
REMOVAL_OUTLINE = "#ef6652"


class SceneChanges:
    def __init__(self, plotter):
        self.plotter = plotter
        self.actors = []

    def update(self, changed, removed):
        self.clear()
        for positions, color in ((changed, ACCENT_OUTLINE), (removed, REMOVAL_OUTLINE)):
            if not positions:
                continue
            bounds = [(position, tuple(value + 1 for value in position)) for position in positions]
            points, lines = box_outlines(bounds)
            mesh = pv.PolyData(points, lines=lines)
            actor = self.plotter.add_mesh(mesh, color=color, opacity=0.9, line_width=2,
                                          lighting=False, pickable=False, reset_camera=False, render=False)
            actor.SetUseBounds(False)
            self.actors.append(actor)
        self.plotter.render()

    def clear(self):
        if not self.actors:
            return
        for actor in self.actors:
            self.plotter.remove_actor(actor, reset_camera=False, render=False)
        self.actors.clear()
        self.plotter.render()


class ChangesController(QObject):
    message = Signal(str)

    def __init__(self, document, tasks, scene_changes):
        super().__init__(scene_changes.plotter)
        self.document = document
        self.tasks = tasks
        self.scene_changes = scene_changes
        self.active = False
        self.token = None

    def set_active(self, enabled):
        enabled = bool(enabled)
        if enabled == self.active:
            return
        self.active = enabled
        if enabled:
            self.refresh()
        else:
            self.token = None
            self.scene_changes.clear()

    def refresh(self):
        if not self.active or self.tasks.busy or self.document.session is None:
            return
        token = (self.document.session_token, self.document.session.dirty)
        if token == self.token:
            return
        self.token = token

        def received(result):
            if token != (self.document.session_token, self.document.session.dirty):
                return
            if result["outlined"]:
                self.scene_changes.update(result["changed"] + result["added"], result["removed"])
            else:
                self.scene_changes.clear()
            self.message.emit(summary(result))

        self.tasks.submit("changes", received, session=self.document.session)

    def reset(self):
        self.token = None
        if self.active:
            self.refresh()
