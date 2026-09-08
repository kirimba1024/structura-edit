import pytest

from structura_edit.picking import Hit
from structura_edit.placement import Placement


def test_surface_placement_and_pin_keep_integer_bounds(edit):
    clipboard = edit.copy(edit.select(((0, 0, 0), (2, 1, 1))))
    model = Placement(clipboard, (0, 0, 0))
    assert model.follow((0, 4, 0), (0, -1, 0), Hit((2, 0, 1), (0, 1, 0)))
    assert model.bounds == ((1, 1, 1), (3, 2, 2))
    assert not model.reason(edit)
    model.nudge((-1, 0, 0))
    assert not model.follow((0, 4, 0), (0, -1, 0), Hit((3, 0, 0), (0, 1, 0)))
    assert model.position == (0, 1, 1) and not model.following
    model.nudge((-1, 0, 0))
    assert not model.reason(edit)


def test_empty_space_uses_placement_height_without_clamping(edit):
    model = Placement(edit.copy(edit.select(((0, 0, 0), (1, 1, 1)))), (0, 0, 0))
    assert model.follow((2.5, 4, 1.5), (0, -1, 0))
    assert model.position == (2, 0, 1)
    assert not model.follow((2.5, 4, 1.5), (1, 0, 0))
    model.follow((2.5, 4, 1.5), (-2, -1, 0))
    assert model.position[0] < 0 and not model.reason(edit)


def test_preparing_placement_does_not_apply_and_checks_combined_budget(edit):
    pytest.importorskip("structura_render")
    from structura_edit.loading import MAX_GEOMETRY_BYTES
    from structura_edit.placement_jobs import prepare_placement

    model = Placement(edit.copy(edit.select(((0, 0, 0), (1, 1, 1)))), (1, 1, 1), take=True)
    with pytest.raises(ValueError, match="geometry"):
        prepare_placement(edit, model, section_bytes={"retained": MAX_GEOMETRY_BYTES})
    assert not edit.dirty and not edit.can_undo
    change, data = prepare_placement(edit, model, section_bytes={})
    assert not edit.dirty and not edit.can_undo
    assert data["sections"] and change
    edit.apply(change)
    assert edit.state_at((0, 0, 0)) == "minecraft:air"
    assert edit.state_at((1, 1, 1)) == "minecraft:stone"
    assert edit.undo() and not edit.can_undo
