from copy import deepcopy

import pytest
from amulet_nbt import IntTag, ListTag
from structura_core import Structure
from structura_core.nbt import load_root, parse_state

from structura_edit import EditSession, StaleChangeError
from structura_edit.picking import pick_block


@pytest.mark.parametrize("origin,direction,position,normal", [
    ((-2, 0.5, 0.5), (1, 0, 0), (0, 0, 0), (-1, 0, 0)),
    ((6, 0.5, 0.5), (-1, 0, 0), (1, 0, 0), (1, 0, 0)),
    ((1.5, 3, 0.5), (0, -1, 0), (1, 0, 0), (0, 1, 0)),
    ((0.5, 0.5, 0.5), (1, 0, 0), (0, 0, 0), (0, 0, 0)),
    ((1, 0.5, 0.5), (-1, 0, 0), (0, 0, 0), (0, 0, 0)),
])
def test_voxel_ray_hits(edit, origin, direction, position, normal):
    hit = pick_block(edit, origin, direction)
    assert hit.position == position
    assert hit.normal == normal
    assert hit.adjacent == tuple(p + n for p, n in zip(position, normal))


def test_voxel_ray_clipping_and_boundaries(edit):
    assert pick_block(edit, (-1, 2, 0), (1, 0, 0)) is None
    assert pick_block(edit, (-1, 0, 0), (-1, 0, 0)) is None
    assert pick_block(edit, (-1, 0, 0), (0, 0, 0)) is None
    edit.apply(edit.set_block((0, 1, 0), "minecraft:glass"))
    assert pick_block(edit, (0.5, 4, 0.5), (0, -1, 0)).position == (0, 1, 0)
    edit.apply(edit.set_block((1, 1, 1), "minecraft:glass"))
    assert pick_block(edit, (-1, -1, 1.5), (1, 1, 0)).position == (1, 1, 1)
    with pytest.raises(ValueError):
        pick_block(edit, (float("nan"), 0, 0), (1, 0, 0))


def test_overlapping_move_preserves_payload_and_undo(edit, structure, tmp_path):
    region = edit.select(((0, 0, 0), (2, 1, 1)))
    move = edit.move(region, (1, 0, 0))
    assert move.removed_block_entities == 0
    assert edit.state_at((0, 0, 0)) == "minecraft:stone"
    edit.apply(move)
    result = Structure(edit.save(tmp_path / "moved.nbt"))
    assert result.name_at((0, 0, 0)) == "minecraft:air"
    assert result.name_at((1, 0, 0)) == "minecraft:stone"
    assert result.name_at((2, 0, 0)) == "minecraft:chest"
    assert result.block_nbt[(2, 0, 0)] == structure.block_nbt[(1, 0, 0)]
    assert result._block_records[(1, 0, 0)]["extra"] == structure._block_records[(0, 0, 0)]["extra"]
    assert result.entities == structure.entities
    assert edit.undo()
    assert load_root(edit.save(tmp_path / "restored.nbt")) == structure._root
    assert edit.redo()
    assert edit.state_at((2, 0, 0)).startswith("minecraft:chest")


def test_move_out_of_bounds_is_atomic_and_duplicate_preserves_source(edit):
    assert not edit.move(edit.select(), (0, 0, 0)) and not edit.dirty
    with pytest.raises(ValueError):
        edit.move(edit.select(), (1, 0, 0))
    assert not edit.dirty
    edit.apply(edit.move(edit.select(((1, 0, 0), (2, 1, 1))), (1, 0, 0), copy=True))
    assert edit.snapshot().block_nbt[(1, 0, 0)] == edit.snapshot().block_nbt[(2, 0, 0)]
    edit.apply(edit.set_block((2, 0, 0), "minecraft:chest[facing=east]"))
    assert (2, 0, 0) in edit.snapshot().block_nbt
    edit.apply(edit.set_block((2, 0, 0), "minecraft:stone"))
    assert (2, 0, 0) not in edit.snapshot().block_nbt


def test_clipboard_is_detached_and_preserves_data_across_documents(structure, tmp_path):
    root = deepcopy(structure._root)
    root["blocks"][1]["nbt"].update({"x": IntTag(1), "y": IntTag(0), "z": IntTag(0)})
    source = EditSession.from_structure(Structure.from_root(root))
    clipboard = source.copy(source.select(((0, 0, 0), (2, 1, 1))))
    source.apply(source.erase(source.select()))
    target = EditSession.from_structure(structure)
    target.apply(target.paste(clipboard, (1, 1, 1)))
    saved = Structure(target.save(tmp_path / "pasted.nbt"))
    assert saved.name_at((1, 1, 1)) == "minecraft:stone"
    assert str(saved._block_records[(1, 1, 1)]["extra"]) == "keep"
    payload = saved.block_nbt[(2, 1, 1)]
    assert tuple(int(payload[axis]) for axis in "xyz") == (2, 1, 1)
    assert payload["Items"] == structure.block_nbt[(1, 0, 0)]["Items"]
    assert saved.entities == structure.entities
    assert target.undo()
    assert load_root(target.save(tmp_path / "undone.nbt")) == structure._root
    assert target.redo()
    assert target.snapshot().block_nbt[(2, 1, 1)] == payload


def test_take_is_deferred_atomic_and_rejects_stale_sources(edit):
    region = edit.select(((0, 0, 0), (2, 1, 1)))
    clipboard = edit.copy(region)
    change = edit.paste(clipboard, (1, 0, 0), take=True)
    assert not edit.dirty and edit.state_at((0, 0, 0)) == "minecraft:stone"
    edit.apply(change)
    assert edit.state_at((0, 0, 0)) == "minecraft:air"
    assert edit.state_at((1, 0, 0)) == "minecraft:stone"
    assert edit.state_at((2, 0, 0)).startswith("minecraft:chest")
    assert edit.undo() and not edit.can_undo and not edit.dirty
    with pytest.raises(StaleChangeError):
        edit.paste(clipboard, (1, 0, 0), take=True)
    assert not edit.dirty and edit.can_redo


def test_paste_skips_air_unless_requested(edit):
    clipboard = edit.copy(edit.select(((2, 0, 0), (3, 1, 1))))
    assert not edit.paste(clipboard, (0, 0, 0))
    edit.apply(edit.paste(clipboard, (0, 0, 0), include_air=True))
    assert edit.state_at((0, 0, 0)) == "minecraft:air"
    assert edit.undo() and not edit.dirty


def test_move_preserves_alternative_palettes(structure, tmp_path):
    root = deepcopy(structure._root)
    palette = root.pop("palette")
    variant = deepcopy(palette)
    variant[0] = parse_state("minecraft:dirt")
    root["palettes"] = ListTag([palette, variant])
    edit = EditSession.from_structure(Structure.from_root(root))
    edit.apply(edit.move(edit.select(((0, 0, 0), (1, 1, 1))), (0, 1, 0)))
    path = edit.save(tmp_path / "variants.nbt")
    assert Structure(path, palette_index=1).name_at((0, 1, 0)) == "minecraft:dirt"


def test_export_rebases_blocks_entities_and_coordinates(structure, tmp_path):
    root = deepcopy(structure._root)
    root["blocks"][1]["nbt"].update({"x": IntTag(1), "y": IntTag(0), "z": IntTag(0)})
    edit = EditSession.from_structure(Structure.from_root(root))
    path = edit.export_selection(edit.select(((1, 0, 0), (3, 2, 2))), tmp_path / "selection.nbt")
    result = Structure(path)
    assert result.size == (2, 2, 2)
    assert result.name_at((0, 0, 0)) == "minecraft:chest"
    assert int(result.block_nbt[(0, 0, 0)]["x"]) == 0
    assert tuple(float(v) for v in result.entities[0]["pos"]) == (0.5, 1.0, 1.5)
    assert not edit.dirty
    assert edit.snapshot().block_nbt[(1, 0, 0)]["x"] == IntTag(1)


def test_shapes_and_masks(edit):
    region = edit.select()
    walls = edit.shape(region, "minecraft:glass", form="Walls")
    expected = {p for p in region.positions() if p[0] in (0, 3) or p[2] in (0, 2)}
    assert set(walls.positions) == expected
    assert set(edit.shape(region, "minecraft:gold_block", mask="minecraft:chest").positions) == {(1, 0, 0)}
    assert set(edit.shape(region, "minecraft:gold_block", surface=True).positions) == {(0, 0, 0), (1, 0, 0)}
    assert set(edit.shape(region, "minecraft:gold_block", form="Top surface").positions) == {(0, 0, 0), (1, 0, 0)}
    ellipse = edit.shape(region, "minecraft:glass", form="Ellipsoid")
    assert (1, 0, 1) in ellipse.positions and (0, 0, 0) not in ellipse.positions
    assert edit.palette_counts(edit.select(((1, 0, 0), (2, 1, 1))), by_state=False) == {"minecraft:chest": 1}


def test_selection_boundary_does_not_expose_an_interior_block(structure):
    root = deepcopy(structure._root)
    root["size"] = ListTag([IntTag(4), IntTag(3), IntTag(3)])
    edit = EditSession.from_structure(Structure.from_root(root))
    edit.apply(edit.fill(edit.select(), "minecraft:stone"))
    selected = edit.select(((1, 1, 1), (2, 2, 2)))
    assert len(edit.shape(selected, "minecraft:glass", surface=True)) == 0
    selected = edit.select(((1, 0, 1), (2, 3, 2)))
    assert len(edit.shape(selected, "minecraft:glass", form="Top surface")) == 1
