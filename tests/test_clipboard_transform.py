import pytest
from structura_core import parse_state, state_key


@pytest.mark.parametrize("state,transform,expected", [
    ("chest", {"turns": 1}, "chest[facing=east]"),
    ("observer", {"turns": 1}, "observer[facing=west]"),
    ("oak_log[axis=x]", {"turns": 1}, "oak_log[axis=z]"),
    ("oak_sign[rotation=15]", {"turns": 1}, "oak_sign[rotation=3]"),
    ("rail[shape=ascending_north]", {"turns": 1}, "rail[shape=ascending_east]"),
    ("rail[shape=north_east]", {"turns": 1}, "rail[shape=south_east]"),
    ("jigsaw[orientation=up_north]", {"turns": 1}, "jigsaw[orientation=up_east]"),
    ("oak_stairs[facing=north,shape=inner_left]", {"turns": 1}, "oak_stairs[facing=east,shape=inner_left]"),
    ("chest[facing=north,type=left]", {"flip": "x"}, "chest[facing=north,type=right]"),
    ("oak_door[facing=west,hinge=left]", {"flip": "x"}, "oak_door[facing=east,hinge=right]"),
    ("oak_stairs[facing=west,shape=outer_left]", {"flip": "x"}, "oak_stairs[facing=east,shape=outer_right]"),
    ("rail[shape=north_west]", {"flip": "x"}, "rail[shape=north_east]"),
    ("oak_sign[rotation=3]", {"flip": "x"}, "oak_sign[rotation=13]"),
    ("oak_sign[rotation=3]", {"flip": "z"}, "oak_sign[rotation=5]"),
    ("redstone_wire[north=up,east=side,south=none,west=none,power=7]", {"turns": 1},
     "redstone_wire[east=up,south=side,west=none,north=none,power=7]"),
])
def test_horizontal_transforms_preserve_block_orientation(edit, state, transform, expected):
    edit.apply(edit.set_block((0, 0, 0), "minecraft:" + state))
    clipboard = edit.copy(edit.select(((0, 0, 0), (1, 1, 1))))
    changed = clipboard.transformed(**transform)
    assert changed.cells[0][1].state == state_key(parse_state("minecraft:" + expected))
    assert edit.state_at((0, 0, 0)) == state_key(parse_state("minecraft:" + state))


def test_asymmetric_take_clears_original_positions_and_preserves_nbt_and_undo(edit):
    clipboard = edit.copy(edit.select(((0, 0, 0), (3, 1, 1))))
    rotated = clipboard.transformed(turns=1)
    assert rotated.size == (1, 1, 3)
    assert rotated.selection == clipboard.selection
    edit.apply(edit.paste(rotated, (3, 0, 0), take=True))
    assert edit.state_at((0, 0, 0)) == edit.state_at((1, 0, 0)) == "minecraft:air"
    assert edit.state_at((3, 0, 0)) == "minecraft:stone"
    assert edit.state_at((3, 0, 1)) == "minecraft:chest[facing=east]"
    assert str(edit.snapshot().block_nbt[(3, 0, 1)]["Items"][0]["id"]) == "minecraft:diamond"
    assert edit.undo() and not edit.dirty and not edit.can_undo
    assert edit.state_at((1, 0, 0)) == "minecraft:chest[facing=north]"
    assert edit.redo() and edit.state_at((3, 0, 1)) == "minecraft:chest[facing=east]"


def test_transform_cycles_preserve_cells_and_pinned_anchor(edit):
    from structura_edit.placement import Placement

    clipboard = edit.copy(edit.select(((0, 0, 0), (3, 1, 2))))
    model = Placement(clipboard, (8, 4, 9), following=False)
    anchor = tuple(p + a for p, a in zip(model.position, model.anchor))
    for _ in range(4):
        model.set_clipboard(model.clipboard.transformed(turns=1))
        assert tuple(p + a for p, a in zip(model.position, model.anchor)) == anchor
        assert not model.following
    for axis in ("x", "z"):
        model.set_clipboard(model.clipboard.transformed(flip=axis).transformed(flip=axis))
    assert model.clipboard.size == clipboard.size and model.position == (8, 4, 9)
    assert [(p, cell.state, cell.data) for p, cell in model.clipboard.cells] == [
        (p, cell.state, cell.data) for p, cell in clipboard.cells]
    for transform in ({"turns": 0.5}, {"turns": True}, {"flip": "y"}):
        with pytest.raises(ValueError):
            clipboard.transformed(**transform)
