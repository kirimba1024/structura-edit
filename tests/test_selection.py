import pytest

from structura_edit.selection import RegionSelection
from structura_edit import Selection


def selection():
    state = RegionSelection()
    state.reset((20, 20, 20))
    return state


def test_click_selects_one_cell_and_another_click_replaces_it():
    state = selection()
    state.select_block((6, 8, 4))
    assert state.region.volume == 1
    assert state.region.lower == (6, 8, 4)
    state.select_block((1, 2, 3))
    assert state.region.volume == 1
    assert state.region.lower == (1, 2, 3)


def test_shift_previews_then_click_commits_inclusive_region():
    state = selection()
    state.select_block((6, 8, 4))
    state.set_extending(True)
    state.hover_block((2, 12, 9))
    assert state.region.volume == 1
    assert state.preview.lower == (2, 8, 4)
    assert state.preview.upper == (7, 13, 10)
    preview = state.preview
    state.select_block((2, 12, 9), extend=True)
    assert state.region == preview
    assert state.anchor == (6, 8, 4)
    state.hover_block((19, 19, 19))
    assert state.preview is None
    assert state.region == preview


def test_release_shift_keeps_previous_selection_and_next_shift_restarts_preview():
    state = selection()
    state.select_block((6, 8, 4))
    state.set_extending(True)
    state.hover_block((0, 0, 0))
    state.set_extending(False)
    assert state.preview is None and state.region.volume == 1
    state.set_extending(True)
    state.hover_block((7, 8, 4))
    assert state.preview.volume == 2
    state.clear()
    assert state.region is None and state.preview is None and state.anchor is None


def test_invalid_bounds_preserve_selection():
    state = selection()
    state.select_all()
    region = state.region
    with pytest.raises(ValueError):
        state.set_bounds((0, 0, 0), (21, 20, 20))
    assert state.region == region


def test_corners_can_cross_each_other_and_change_independently():
    state = selection()
    state.set_corner(0, (8, 2, 9))
    state.set_corner(1, (2, 6, 3))
    assert state.region == Selection((2, 2, 3), (9, 7, 10))
    state.set_corner(0, (1, 8, 1))
    assert state.opposite == (2, 6, 3)
    assert state.region == Selection((1, 6, 1), (3, 9, 4))
    before = state.region, state.anchor, state.opposite
    with pytest.raises(ValueError):
        state.set_corner(1, (20, 0, 0))
    assert (state.region, state.anchor, state.opposite) == before
    state.clear()
    state.set_corner(1, (4, 3, 2))
    assert state.region.volume == 1 and state.anchor == state.opposite == (4, 3, 2)


def test_adjustment_preserves_anchor_side_and_shift_preview_uses_adjusted_corner():
    state = selection()
    state.select_block((8, 2, 9))
    state.select_block((2, 6, 3), extend=True)
    original = state.region
    state.adjust("grow", 1)
    state.adjust("shift", (3, 2, -1))
    assert state.region == Selection((4, 3, 1), (13, 10, 10))
    assert state.anchor == (12, 3, 9)
    state.set_extending(True)
    state.hover_block((14, 5, 8))
    assert state.preview == Selection((12, 3, 8), (15, 6, 10))
    state.adjust("shift", (-3, -2, 1))
    state.adjust("grow", -1)
    assert state.region == original and state.anchor == (8, 2, 9)
    assert state.preview is None


@pytest.mark.parametrize("mode,value", [("shift", (-3, 0, 0)), ("shift", (18, 0, 0)),
                                       ("grow", 3), ("grow", -2)])
def test_invalid_adjustment_is_atomic(mode, value):
    state = selection()
    state.set_bounds((2, 2, 2), (6, 6, 6))
    before = state.region, state.anchor
    with pytest.raises(ValueError):
        state.adjust(mode, value)
    assert (state.region, state.anchor) == before


def test_region_transforms_do_not_depend_on_volume():
    region = Selection.from_corners((1_000_000, 10, 20), (2_000_000, 30, 40))
    assert region.expanded(2).expanded(-2) == region
    moved = region.shifted((-10, 2, 0))
    assert moved.volume == region.volume and region.lower == (1_000_000, 10, 20)
    for value in (True, 1.5):
        with pytest.raises(ValueError):
            region.expanded(value)
