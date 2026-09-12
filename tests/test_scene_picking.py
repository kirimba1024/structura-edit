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


def test_selection_uses_visible_geometry_during_world_area_replacement():
    scene = Scene(None)
    scene.display_revision = 3
    scene.display_state = SimpleNamespace(_id="world", revision=3, origin=(0, 0, 0), size=(32, 16, 32),
                                         state_at=lambda p: "minecraft:stone" if p == (20, 4, 20) else None)
    scene.ray_at = lambda _: ((4.5, 4.5, 0), (0, 0, 1))
    session = SimpleNamespace(_id="world", revision=4, origin=(16, 0, 16), size=(32, 16, 32),
                              state_at=lambda p: "minecraft:stone" if p == (4, 4, 4) else None)
    hit, entity = scene.target_at(session, None)
    assert hit.position == (4, 4, 4) and entity is None
    assert scene.hit_at(session, None) == hit
    session.state_at = lambda p: "minecraft:gold_block" if p == (4, 4, 4) else None
    assert scene.target_at(session, None) == (None, None)
    assert scene.hit_at(session, None) is None


def test_visible_old_area_cannot_select_outside_new_loaded_data():
    scene = Scene(None)
    scene.display_state = SimpleNamespace(_id="world", origin=(0, 0, 0), size=(32, 16, 32),
                                         state_at=lambda p: "minecraft:stone" if p == (4, 4, 4) else None)
    scene.ray_at = lambda _: ((-11.5, 4.5, -16), (0, 0, 1))
    session = SimpleNamespace(_id="world", origin=(16, 0, 16), size=(32, 16, 32),
                              state_at=lambda p: pytest.fail("Read outside loaded data"))
    assert scene.target_at(session, None) == (None, None)
