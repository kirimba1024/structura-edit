from .scene_geometry import add_geometry, remove_geometry


class SourceCut:
    def __init__(self, scene):
        self.scene = scene
        self.originals = []
        self.actors = []

    def load(self, data):
        self.clear()
        if data is None:
            return
        actors = []
        try:
            for key, section in data['sections'].items():
                actors.extend(add_geometry(self.scene.plotter, section))
        except Exception:
            remove_geometry(self.scene.plotter, actors)
            raise
        self.actors = actors
        self.originals = [actor for key in data['sections'] for actor in self.scene.sections.get(key, ())]
        self.show(True)

    def show(self, visible):
        for actor in self.originals:
            actor.SetVisibility(not visible)
        for actor in self.actors:
            actor.SetVisibility(visible)

    def clear(self):
        self.show(False)
        remove_geometry(self.scene.plotter, self.actors)
        self.originals, self.actors = [], []
