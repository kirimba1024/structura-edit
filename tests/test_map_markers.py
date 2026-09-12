import numpy as np
import pytest

from structura_edit.map_entities import MapMarkers
from structura_edit.map_projection import VIEWS, depth_axis, project


@pytest.mark.parametrize("view", VIEWS)
@pytest.mark.parametrize("origin", ((0, 0, 0), (-1024, -64, 256)))
@pytest.mark.parametrize("cave_y", (None, 32))
def test_marker_culling_matches_all_projections_slices_and_cave_levels(view, origin, cave_y):
    positions = np.random.default_rng(17).uniform(-16, 80, (256, 3))
    center = project(tuple(p + o for p, o in zip((32, 32, 32), origin)), (0, 0, 0), view)
    area = center[0] - 24, center[1] - 20, center[0] + 24, center[1] + 20
    expected, projected = [], []
    for index, position in enumerate(positions):
        if view != "bottom" and not 12 <= position[depth_axis(view)] < 52:
            continue
        if view == "bottom" and cave_y is not None and abs(position[1] - cave_y) > 16:
            continue
        point = project(tuple(p + o for p, o in zip(position, origin)), (0, 0, 0), view)
        if area[0] <= point[0] <= area[2] and area[1] <= point[1] <= area[3]:
            expected.append(index)
            projected.append(point)
    indices, points = MapMarkers(positions).visible(view, origin, area, (12, 52), cave_y)
    assert list(indices) == expected
    assert np.allclose(points, np.asarray(projected).reshape(-1, 2))


def test_marker_edges_empty_sets_and_origin_changes():
    markers = MapMarkers([(0, 0, 0), (10, 1, 10), (5, 2, 5)])
    indices, points = markers.visible("top", (0, 0, 0), (0, 0, 10, 10), (0, 2))
    assert list(indices) == [0, 1]
    indices, shifted = markers.visible("top", (-20, 0, 30), (-20, 30, -10, 40), (0, 2))
    assert list(indices) == [0, 1]
    assert np.array_equal(shifted, points + (-20, 30))
    indices, points = MapMarkers([]).visible("bottom", (0, 0, 0), (0, 0, 10, 10), (0, 2))
    assert not len(indices) and points.shape == (0, 2)
