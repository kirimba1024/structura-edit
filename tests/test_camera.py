from types import SimpleNamespace

import numpy as np
import pytest

from structura_edit.camera import FreeCamera

pv = pytest.importorskip("pyvista")


@pytest.fixture
def camera():
    view = SimpleNamespace(camera=pv.Camera(), bounds=(0, 10, 0, 10, 0, 10), render=lambda: None)
    camera = FreeCamera(view, lambda position, direction: None)
    view.camera.position = (5, 5, 15)
    view.camera.focal_point = (5, 5, 5)
    view.camera.up = (0, 1, 0)
    return camera


def test_flight_translates_camera_and_target_without_zoom_or_collisions(camera):
    vtk = camera.plotter.camera
    angle = vtk.view_angle
    camera.step((0, 0, 1), 8, 2)
    assert np.allclose(vtk.position, (5, 5, -1))
    assert np.allclose(vtk.focal_point, (5, 5, -11))
    camera.step((0, 0, -1), 8, 2)
    assert np.allclose(vtk.position, (5, 5, 15))
    assert vtk.view_angle == angle
    assert not vtk.parallel_projection


def test_look_rotates_at_fixed_position_and_limits_pitch(camera):
    vtk = camera.plotter.camera
    position = vtk.position
    angle = vtk.view_angle
    camera.look(100, -100)
    assert vtk.position == position
    assert vtk.direction[0] > 0 and vtk.direction[1] > 0
    camera.look(0, -100000)
    assert np.isfinite(vtk.direction).all()
    assert vtk.direction[1] < 1
    camera.look(0, 100000)
    assert vtk.direction[1] > -1
    assert vtk.position == position
    assert vtk.view_angle == angle


def test_diagonal_flight_has_constant_speed_and_is_time_based(camera):
    vtk = camera.plotter.camera
    start = np.asarray(vtk.position)
    camera.step((1, 0, 1), 8, 0.2)
    diagonal = np.asarray(vtk.position) - start
    assert diagonal[0] > 0 and diagonal[2] < 0
    assert np.isclose(np.linalg.norm(diagonal), 1.6)
    camera.move_to(start)
    for _ in range(20):
        camera.step((1, 0, 1), 8, 0.01)
    assert np.allclose(np.asarray(vtk.position) - start, diagonal)
