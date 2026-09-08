import pytest

from structura_edit.selection import RegionSelection


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
