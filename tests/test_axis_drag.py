import numpy as np
import pytest

from structura_edit.axis_drag import AxisDrag


@pytest.mark.parametrize("delta,expected", [(2.4, 2), (2.6, 3), (-0.5, -1), (-2.6, -3)])
def test_drag_snaps_only_selected_axis(delta, expected):
    position = (4, -3, 7)
    anchor = np.array((4.5, -2.5, 7.5))
    origin = anchor + (0, 0, 10)
    direction = (0, 0, -1)
    drag = AxisDrag.begin(position, anchor, 0, direction, (origin, direction))
    assert drag.moved((origin + (delta, 0.7, 0), direction)) == (4 + expected, -3, 7)
    assert drag.moved((origin, direction)) == position


def test_camera_parallel_axis_is_not_draggable():
    assert AxisDrag.begin((0, 0, 0), (0, 0, 0), 1, (0, -1, 0), ((0, 10, 0), (0, -1, 0))) is None


def test_drag_handles_perspective_and_parallel_ray_without_jumping():
    anchor = np.zeros(3)
    origin = (10, 5, 10)
    drag = AxisDrag.begin((0, 0, 0), anchor, 1, (-10, -5, -10), (origin, (-10, -5, -10)))
    assert drag.moved((origin, (-10, -1, -10))) == (0, 4, 0)
    assert drag.moved((origin, (0, 1, 0))) is None
