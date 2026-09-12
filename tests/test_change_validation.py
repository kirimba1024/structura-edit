from copy import deepcopy
from dataclasses import FrozenInstanceError, asdict, replace
import pickle

import numpy as np
import pytest

from structura_edit import EditSession, StaleChangeError
from structura_edit.cell_data import CellData
from structura_edit.changes import _Cell, _Delta


@pytest.mark.parametrize("fixture", ("edit", "world_edit"))
def test_cell_matching_preserves_air_holes_variants_nbt_and_overlays(request, fixture):
    session = request.getfixturevalue(fixture)
    positions = ((0, 0, 0), (1, 0, 0), (2, 0, 0), (3, 0, 0), (0, 1, 0))
    cells = [None, _Cell("minecraft:air"), *(session._cell(position) for position in positions)]
    for overlay in ({}, {(0, 0, 0): _Cell("minecraft:glass"), (0, 1, 0): _Cell("minecraft:air")}):
        session._cells = overlay
        for position in positions:
            for cell in cells:
                assert session._cell_matches(position, cell) == (session._cell(position) == cell)


def test_session_subclass_keeps_custom_cell_lookup(structure):
    class CustomSession(EditSession):
        def _cell(self, position):
            return _Cell("minecraft:gold_block")
    session = CustomSession.from_structure(structure)
    assert session._cell_matches((0, 0, 0), _Cell("minecraft:gold_block"))
    assert not session._cell_matches((0, 0, 0), session._original((0, 0, 0)))


@pytest.mark.parametrize("position", ((0, 1), (0, 1, 0, 0), (False, 1, 0), (0.0, 1, 0), (0, 1.5, 0), "010"))
def test_malformed_positions_fail_before_mutation(edit, position):
    change = edit.set_block((0, 1, 0), "minecraft:glass")
    invalid = replace(change, changes=(replace(change.changes[0], position=position),))
    with pytest.raises(ValueError, match="three integers"):
        edit.apply(invalid)
    assert edit.revision == 0 and not edit.dirty and not edit.can_undo


def test_numpy_integer_coordinates_remain_supported(edit):
    change = edit.set_block((0, 1, 0), "minecraft:glass")
    position = tuple(np.int64(value) for value in (0, 1, 0))
    edit.apply(replace(change, changes=(replace(change.changes[0], position=position),)))
    assert edit.state_at((0, 1, 0)) == "minecraft:glass"


@pytest.mark.parametrize("fields", (
    dict(state="minecraft:dirt"), dict(variant=None), dict(keep_nbt=True), dict(origin=None), dict(data=CellData(record="{}")),
))
def test_every_before_cell_field_is_validated(edit, fields):
    change = edit.set_block((0, 0, 0), "minecraft:glass")
    delta = change.changes[0]
    with pytest.raises(StaleChangeError):
        edit.apply(replace(change, changes=(replace(delta, before=replace(delta.before, **fields)),)))
    assert edit.revision == 0 and not edit.can_undo


@pytest.mark.parametrize("fields", (
    dict(origin=(0, 1, 0)), dict(origin=(0.0, 0, 0)), dict(variant=999), dict(state="glass"),
    dict(keep_nbt=True), dict(keep_nbt=True, data=CellData(record="{}")),
))
def test_source_palette_canonical_state_and_nbt_checks_remain(edit, fields):
    change = edit.set_block((0, 0, 0), "minecraft:glass")
    delta = change.changes[0]
    with pytest.raises(ValueError):
        edit.apply(replace(change, changes=(replace(delta, after=replace(delta.after, **fields)),)))
    assert edit.revision == 0 and not edit.can_undo


def test_duplicate_cells_fail_atomically(edit):
    change = edit.set_block((0, 0, 0), "minecraft:glass")
    with pytest.raises(ValueError, match="duplicate"):
        edit.apply(replace(change, changes=change.changes * 2))
    assert edit.revision == 0


def test_compact_cells_preserve_dataclass_and_pickle_contracts():
    cell = _Cell("minecraft:chest", 2, True, (1, 2, 3), CellData('{id:"minecraft:chest"}', '{custom:1}'))
    delta = _Delta((-1, 2, 3), None, cell)
    assert asdict(cell)["data"] == dict(nbt='{id:"minecraft:chest"}', record='{custom:1}')
    assert replace(cell, variant=None).origin == cell.origin
    for protocol in range(pickle.HIGHEST_PROTOCOL + 1):
        restored = pickle.loads(pickle.dumps(delta, protocol=protocol))
        assert restored == delta and restored.after is not cell
        assert hash(restored.after) == hash(cell)
    assert deepcopy(delta) == delta
    with pytest.raises(FrozenInstanceError):
        cell.state = "minecraft:air"
