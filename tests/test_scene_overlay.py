import numpy as np
import pytest

from structura_edit.changes import Selection

pv = pytest.importorskip("pyvista")


def test_selection_can_be_drawn_before_the_resized_scene_arrives():
    from structura_edit.cell_set import CellSet
    from structura_edit.scene_overlay import SceneOverlay

    region = Selection((0, 0, 0), (32, 144, 24))
    temporary = CellSet.from_positions(((1, 2, 3), (4, 5, 6)))
    view = pv.Plotter(off_screen=True)
    overlay = SceneOverlay(view)
    try:
        overlay.set_selection(region, temporary, ((0, 0, 0), (31, 143, 23)), offset=(-40, -3, -32))
        assert overlay.selection.bounds == ((-40, -3, -32), (-8, 141, -8))
        assert overlay.temporary.bounds == ((-39, -1, -29), (-35, 3, -25))
        assert overlay.corners == ((-40, -3, -32), (-9, 140, -9))
        assert region.lower == (0, 0, 0) and temporary.volume == 2
        overlay.set_selection(region)
        assert overlay.selection.bounds == (region.lower, region.upper)
        assert overlay.temporary.bounds is None and overlay.corners == ()
    finally:
        view.close()


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


def test_placement_markers_stay_cleared_after_visibility_updates():
    from structura_edit.placement_view import PlacementView

    view = pv.Plotter(off_screen=True, window_size=(400, 300))
    placement = PlacementView(view)
    markers = placement.bounds, placement.anchor, placement.source
    try:
        for marker in markers:
            marker.set_bounds(((1, 2, 3), (4, 5, 6)))
        placement.set_visible(False)
        assert not any(actor.GetVisibility() for marker in markers for actor in marker.actors)
        placement.set_visible(True)
        assert all(actor.GetVisibility() for marker in markers for actor in marker.actors)
        placement.source.set_bounds(None)
        placement.set_visible(True)
        assert not any(actor.GetVisibility() for actor in placement.source.actors)
        assert all(actor.GetVisibility() for actor in placement.bounds.actors)
        placement.clear()
        for visible in (True, False, True):
            placement.set_visible(visible)
            assert not any(actor.GetVisibility() for marker in markers for actor in marker.actors)
    finally:
        view.close()
