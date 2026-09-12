from types import SimpleNamespace

import numpy as np
import pytest

from structura_edit.height_slice import HeightSlice
from structura_edit.map_picking import pick_map_block
from structura_edit.map_projection import VIEWS, depth_axis


def column_session():
    return SimpleNamespace(size=(8, 12, 8), origin=(-32, -64, 16),
                           state_at=lambda p: 'minecraft:stone' if p[1] in (1, 5, 10) else None)


@pytest.mark.parametrize('view', VIEWS)
def test_map_picks_the_visible_surface_and_respects_the_cut(view):
    axis = depth_axis(view)
    session = SimpleNamespace(size=(8, 8, 8), origin=(-32, -64, 16),
                              state_at=lambda p: 'minecraft:stone' if p[axis] in (1, 4, 6) else None)
    position = (2.25, 2.25, 2.25)
    positive = view in ('top', 'south', 'east')
    assert pick_map_block(session, position, view).position[axis] == (6 if positive else 1)
    assert pick_map_block(session, position, view, (4, 4, 4)).position[axis] == 4
    empty = (-1, -1, -1) if positive else (8, 8, 8)
    assert pick_map_block(session, position, view, empty) is None


def test_cave_pick_uses_the_same_floor_rule_as_the_map():
    session = column_session()
    for view in ('top', 'bottom'):
        assert pick_map_block(session, (2.25, 6, 3.25), view, (2, 6, 3), 6).position == (2, 5, 3)
    assert pick_map_block(session, (2.25, 6, 3.25), 'top', height=HeightSlice('below', -60)).position == (2, 1, 3)
    assert pick_map_block(session, (-.25, 6, 3.25), 'top') is None


def test_map_icon_hit_follows_draw_order_and_off_mode(qt_app):
    from structura_edit.map_canvas import MapCanvas

    canvas = MapCanvas()
    canvas.resize(600, 400)
    canvas.size_blocks = (8, 8, 8)
    canvas.origin = (-32, -64, 16)
    canvas.position = (4, 4, 4)
    canvas.layout.large = True
    canvas.layout.focused = 'top'
    canvas.entity_mode = 'Icons'
    icon = np.full((16, 16, 4), 255, np.uint8)
    canvas.set_entities([((4, 4, 4), False, 'First', icon), ((4, 4, 4), False, 'Second', icon)], ('first', 'second'))
    results = []
    canvas.picked.connect(lambda *args: results.append(args))
    try:
        point = canvas.screen_point((4, 4, 4), 'top')
        canvas.pick('top', point, True)
        assert results[-1][2:] == ('second', True)
        assert results[-1][1] == pytest.approx((4, 4, 4))
        canvas.entity_mode = 'Off'
        canvas.pick('top', point)
        assert results[-1][2] is None
    finally:
        canvas.deleteLater()
