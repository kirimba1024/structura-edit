from collections import deque
from time import perf_counter

from PySide6.QtCore import QObject, QTimer


class SceneRetirement(QObject):
    def __init__(self, plotter):
        super().__init__(plotter)
        self.plotter = plotter
        self.actors = deque()
        self.timer = QTimer(self)
        self.timer.setInterval(4)
        self.timer.timeout.connect(self.step)

    @property
    def busy(self):
        return bool(self.actors)

    def add(self, actors):
        for actor in actors:
            actor.SetVisibility(False)
            self.actors.append(actor)
        if self.actors and not self.timer.isActive():
            self.timer.start()

    def step(self):
        deadline = perf_counter() + .001
        while self.actors and perf_counter() < deadline:
            actor = self.actors.popleft()
            self.plotter.renderer.RemoveActor(actor)
            del actor
        if not self.actors:
            self.timer.stop()

    def close(self):
        self.timer.stop()
        while self.actors:
            self.plotter.renderer.RemoveActor(self.actors.popleft())
