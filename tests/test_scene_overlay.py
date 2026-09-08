import numpy as np
import pytest

from structura_edit.changes import Selection

pv = pytest.importorskip("pyvista")


def test_overlay_is_redrawn_and_cleared_with_scene_frames():
    from structura_edit.scene_overlay import SceneOverlay

    view = pv.Plotter(off_screen=True, window_size=(400, 300))
    view.set_background("#cfe6ed")
    overlay = SceneOverlay(view)
    try:
        view.camera.position = (5, 4, 5)
        view.camera.focal_point = (0.5, 0.5, 0.5)
        view.camera.up = (0, 1, 0)
        view.camera.clipping_range = (0.1, 100)
        view.show(auto_close=False)
        clean = view.screenshot()
        actor_count = view.renderer.GetViewProps().GetNumberOfItems()
        overlay.set_selection(Selection((0, 0, 0), (1, 1, 1)), corners=((0, 0, 0), (0, 0, 0)))
        for actor in overlay.selection.actors:
            actor.SetVisibility(False)
        view.render()
        selected = view.screenshot()
        assert np.count_nonzero(selected != clean) > 100
        for offset in range(1, 8):
            view.camera.position = (5 + offset, 4, 5)
            view.render()
        view.camera.position = (5, 4, 5)
        view.render()
        assert np.array_equal(view.screenshot(), selected)
        overlay.set_selection(None)
        assert np.array_equal(view.screenshot(), clean)
        overlay.set_looking(True)
        assert np.count_nonzero(view.screenshot() != clean) > 10
        overlay.set_looking(False)
        assert np.array_equal(view.screenshot(), clean)
        assert view.renderer.GetViewProps().GetNumberOfItems() == actor_count
        assert not overlay.actor.GetPickable()
    finally:
        view.close()
