from itertools import product

import numpy as np
import pytest

from structura_edit.scene_lines import box_outlines


@pytest.mark.parametrize("bounds", [[], [((-3, -2, -1), (2, 4, 6)), ((10.5, 0, 0), (11, 1, 1))]])
def test_outlines_keep_twelve_edges_inside_each_box(bounds):
    points, lines = box_outlines(bounds)
    assert points.shape == (8 * len(bounds), 3)
    segments = lines.reshape(-1, 3)
    assert len(segments) == 12 * len(bounds)
    for index, (lower, upper) in enumerate(bounds):
        corners = points[index * 8:(index + 1) * 8]
        assert set(map(tuple, corners)) == set(product(*zip(lower, upper)))
        edges = segments[index * 12:(index + 1) * 12]
        assert np.all(edges[:, 0] == 2)
        assert np.all((edges[:, 1:] >= index * 8) & (edges[:, 1:] < (index + 1) * 8))
        assert len({tuple(sorted(edge)) for edge in edges[:, 1:]}) == 12
        assert np.all(np.sum(points[edges[:, 1]] != points[edges[:, 2]], axis=1) == 1)
