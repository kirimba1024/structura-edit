from types import SimpleNamespace

import pytest

from structura_edit.overview_scene import OverviewScene


class Actor:
    def SetVisibility(self, visible):
        self.visible = visible

    def SetPosition(self, *position):
        self.position = position

    def SetPickable(self, pickable):
        self.pickable = pickable


@pytest.mark.parametrize("cancel", [False, True])
def test_replacement_is_hidden_and_cancel_cannot_publish_a_partial_batch(monkeypatch, cancel):
    actors = []
    plotter = SimpleNamespace(remove_actor=lambda actor, **kwargs: actors.remove(actor))
    scene = OverviewScene(plotter)
    def produce(*args, **kwargs):
        for _ in range(3):
            actor = Actor()
            actors.append(actor)
            yield actor
    monkeypatch.setattr("structura_edit.overview_scene.add_geometry_steps", produce)
    data = dict(origin=(256, 0, 0), meshes=[], flat=[], colored=[])
    scene.begin(["old"])
    list(scene.add_steps("old", data, 12))
    assert scene.publish((16, 0, 0))
    previous = actors.copy()
    scene.begin(["new"])
    steps = scene.add_steps("new", data, 12)
    next(steps)
    assert all(actor.visible for actor in previous) and not actors[-1].visible
    assert not scene.publish((32, 0, 0))
    if cancel:
        steps.close()
        scene.cancel()
        assert actors == previous and scene.visible == {"old"}
    else:
        list(steps)
        assert scene.publish((32, 0, 0))
        assert all(actor.visible and actor.position == (224, 0, 0) for actor in actors)
        assert all(actor not in actors for actor in previous) and scene.visible == {"new"}
