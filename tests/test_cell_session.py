import pytest
from structura_core.nbt import load_root

from structura_edit import CellSet


def as_map(change):
    return {delta.position: ((delta.before.state if delta.before else None), delta.after.state) for delta in change.changes}


@pytest.mark.parametrize("bounds", [
    ((0, 0, 0), (4, 2, 3)),
    ((0, 0, 0), (1, 2, 3)),
    ((0, 0, 0), (4, 1, 3)),
    ((0, 0, 1), (4, 2, 3)),
    ((1, 1, 1), (3, 2, 2)),
])
def test_operations_match_box_selection(edit, bounds):
    box = edit.select(bounds)
    cells = CellSet.from_box(box)
    assert as_map(edit.fill(cells, "minecraft:stone")) == as_map(edit.fill(box, "minecraft:stone"))
    left = edit.replace(cells, "minecraft:stone", "minecraft:gold_block")
    right = edit.replace(box, "minecraft:stone", "minecraft:gold_block")
    assert as_map(left) == as_map(right)
    for form in ("Walls", "Shell", "Ellipsoid", "Cylinder", "Top surface"):
        left = edit.shape(cells, "minecraft:stone", form=form)
        right = edit.shape(box, "minecraft:stone", form=form)
        assert as_map(left) == as_map(right), form


def test_selection_outside_document_is_rejected(edit):
    with pytest.raises(ValueError):
        edit.fill(CellSet.from_positions([(4, 0, 0)]), "minecraft:stone")
    with pytest.raises(ValueError):
        edit.fill(CellSet.from_positions([(-1, 0, 0)]), "minecraft:stone")


def test_palette_counts_partial_cells_with_document_bounds(edit):
    cells = CellSet.from_box(edit.select(((0, 0, 0), (4, 2, 3))))
    cells = cells.difference(CellSet.from_positions([(1, 0, 0)]))
    assert cells.lower == (0, 0, 0) and cells.upper == edit.size
    counts = edit.palette_counts(cells)
    assert sum(counts.values()) == 3
    assert counts.get("minecraft:chest") is None
    assert counts["minecraft:stone"] == 1


def test_export_selection_matches_box(edit, tmp_path):
    box = edit.select(((0, 0, 0), (2, 2, 1)))
    left = edit.export_selection(CellSet.from_box(box), tmp_path / "cells.nbt")
    right = edit.export_selection(box, tmp_path / "box.nbt")
    assert load_root(left) == load_root(right)


def test_move_on_cells_touches_only_footprint(edit):
    cells = CellSet.from_box(edit.select(((0, 0, 0), (2, 1, 1)))).difference(CellSet.from_positions([(1, 0, 0)]))
    touched = {delta.position for delta in edit.move(cells, (0, 1, 0), copy=True).changes}
    assert (0, 1, 0) in touched and (1, 1, 0) not in touched
    assert edit.state_at((1, 0, 0)).startswith("minecraft:chest")


def test_stack_on_cells_respects_footprint(edit):
    cells = CellSet.from_box(edit.select(((0, 0, 0), (2, 1, 1)))).difference(CellSet.from_positions([(1, 0, 0)]))
    touched = {delta.position for delta in edit.stack(cells, 1, (0, 0, 1)).changes}
    assert (0, 0, 1) in touched and (1, 0, 1) not in touched


def test_transformed_clipboard_keeps_footprint(edit):
    cells = CellSet.from_box(edit.select(((0, 0, 0), (2, 1, 2)))).difference(CellSet.from_positions([(1, 0, 0)]))
    clipboard = edit.copy(cells)
    turned = clipboard.transformed(turns=1)
    assert turned.footprint is not None and turned.footprint.volume == clipboard.footprint.volume
    assert (1, 0, 1) not in turned.footprint and (1, 0, 0) in turned.footprint
