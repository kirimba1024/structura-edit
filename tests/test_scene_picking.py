from types import SimpleNamespace

import numpy as np
import pytest

from structura_edit.scene import Scene


@pytest.mark.parametrize("bounds, expected", [
    (((.2, .2, 1), (.8, .8, 2)), "entity:0"),
    (((.2, .2, 4), (.8, .8, 5)), None),
    (((2, 0, 1), (3, 1, 2)), None),
])
def test_hover_and_click_share_nearest_visible_target(bounds, expected):
    scene = Scene(None)
    scene.entity_keys = ("entity:0",)
    scene.entity_boxes = np.asarray([bounds])
    scene.ray_at = lambda _: ((.5, .5, 0), (0, 0, 1))
    session = SimpleNamespace(size=(4, 4, 8), state_at=lambda p: "minecraft:stone" if p == (0, 0, 3) else None)
    block, entity = scene.target_at(session, None)
    assert entity == expected
    assert (block.position if block else None) == ((0, 0, 3) if expected is None else None)
    assert scene.entity_at(session, None) == expected
