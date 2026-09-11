from dataclasses import replace

import pytest

from structura_edit import EditSession
from structura_edit.cell_set import CellSet
from structura_edit.changes import _Cell
from structura_edit.inspection import inspect_selection


class NoScan(dict):
    def __iter__(self):
        raise AssertionError('Whole document scanned')


def test_small_replace_copy_counts_and_surface_do_not_scan_source(edit):
    edit._document.source.present = NoScan(edit._document.source.present)
    selection = edit.select(((0, 0, 0), (1, 1, 1)))
    assert len(edit.replace(selection, 'minecraft:stone', 'minecraft:glass')) == 1
    assert edit.copy(selection).block_count == 1
    assert edit.palette_counts(selection) == {'minecraft:stone': 1}
    assert len(edit.shape(selection, 'minecraft:glass', form='Top surface')) == 1


def test_inspection_of_small_region_does_not_scan_large_overlay(structure):
    structure.size = (256, 2, 3)
    edit = EditSession.from_structure(structure)
    edit._cells = NoScan({(x, 0, 0): _Cell('minecraft:gold_block') for x in range(256)})
    result = inspect_selection(edit, edit.select(((0, 0, 0), (64, 1, 1))))
    assert '64 total · 1 material' in result['facts']
    assert len(result['source'].present) == 32


def test_sparse_copy_paste_stack_count_stored_objects_and_preserve_air_footprint(structure):
    structure.size = (1000, 10, 100)
    structure.present = {(0, 0, 0): 0, (1, 0, 0): 1, (2, 0, 0): 2}
    edit = EditSession.from_structure(structure, operation_limit=20)
    edit._cells[(998, 0, 99)] = _Cell('minecraft:gold_block')
    clipboard = edit.copy(edit.select())
    assert len(clipboard.cells) == 4 and clipboard.block_count == 3
    assert clipboard.size == edit.size
    target = edit.paste(clipboard, (0, 0, 0), include_air=False)
    edit._check_change(target)
    change = edit.stack(edit.select(), 2, (0, 10, 0))
    assert len(change.changes) == 6
    assert len(change.entities) == 2
    with pytest.raises(ValueError, match='object budget'):
        edit.paste(clipboard, (0, 0, 0), include_air=True)
    with pytest.raises(ValueError, match='cell budget'):
        edit.stack(edit.select(), 2, (0, 10, 0), include_air=True)
    with pytest.raises(ValueError, match='object budget'):
        edit.paste(replace(clipboard, entities=clipboard.entities * 30), (0, 0, 0))


def test_sparse_cell_set_copy_preserves_holes_when_pasting_air(edit):
    selection = CellSet.from_positions(((0, 0, 0), (2, 0, 0), (3, 1, 2)))
    clipboard = edit.copy(selection, include_entities=False)
    change = edit.paste(clipboard, (0, 0, 0), include_air=True)
    assert set(change.positions) <= set(selection.positions())
    assert (3, 1, 2) in change.positions
    assert (1, 0, 0) not in change.positions


def test_copy_stops_at_stored_object_budget(edit):
    edit.operation_limit = 1
    with pytest.raises(ValueError, match='object budget'):
        edit.copy(edit.select())


def test_sparse_world_copy_still_rejects_missing_chunks(world_edit):
    world_edit.loaded_chunks = frozenset()
    with pytest.raises(ValueError, match='absent'):
        world_edit.copy(world_edit.select())


@pytest.mark.parametrize('sparse', [False, True])
def test_adaptive_copy_and_replace_match_exhaustive_reference(edit, sparse):
    selection = edit.select() if not sparse else CellSet.from_positions(((0, 0, 0), (2, 0, 0), (3, 1, 2)))
    edit.apply(edit.set_block((3, 1, 2), 'minecraft:stone'))
    expected = {p for p in selection.positions() if (edit._cell(p) is not None and edit._cell(p).state == 'minecraft:stone')}
    assert set(edit.replace(selection, 'minecraft:stone', 'minecraft:glass').positions) == expected
    clipboard = edit.copy(selection)
    assert set(clipboard.sources) == {p for p in selection.positions() if edit._cell(p) is not None}
