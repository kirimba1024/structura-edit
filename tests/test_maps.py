import numpy as np
import pytest

from structura_edit.map_projection import VIEWS, project, unproject


@pytest.mark.parametrize("view", VIEWS)
def test_map_coordinates_roundtrip(view):
    point, size = (1.25, 2.5, 3.75), (12, 8, 16)
    assert np.allclose(unproject(project(point, size, view), point, size, view), point)


def test_all_six_maps_are_built_and_bounded(edit):
    pytest.importorskip("structura_render")
    from structura_edit.map_images import build_maps
    images = build_maps(edit)
    assert set(images) == set(VIEWS)
    assert all(image.dtype == np.uint8 and image.ndim == 3 for image in images.values())
    assert sum(image.shape[0] * image.shape[1] for image in images.values()) <= 1_000_000
    with pytest.raises(ValueError, match="budget"):
        build_maps(edit, max_pixels=1)
