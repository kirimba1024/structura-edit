from copy import deepcopy
from collections import Counter
from dataclasses import replace
import random
import subprocess
import sys

import pytest
from amulet_nbt import IntTag, ListTag, StringTag
from structura_core import Structure
from structura_core.nbt import parse_state, load_root

from structura_edit import EditSession, Selection, StaleChangeError


def test_preview_apply_undo_save_preserves_authored_data(edit, structure, tmp_path):
    before = deepcopy(structure._root)
    change = edit.replace(edit.select(), "minecraft:stone", "minecraft:gold_block")
    assert len(change) == 1
    assert edit.state_at((0, 0, 0)) == "minecraft:stone"
    assert edit.snapshot(change).name_at((0, 0, 0)) == "minecraft:gold_block"
    assert edit.apply(change) == 1
    assert edit.dirty
    output = edit.save(tmp_path / "edited.nbt")
    root = load_root(output)
    for key in ("custom", "author", "entities", "DataVersion", "size"):
        assert root[key] == before[key]
    assert root["blocks"][0]["extra"] == before["blocks"][0]["extra"]
    assert root["blocks"][1]["nbt"] == before["blocks"][1]["nbt"]
    assert Structure(output).name_at((0, 0, 0)) == "minecraft:gold_block"
    assert not edit.dirty
    assert edit.undo() and edit.dirty
    assert edit.redo() and not edit.dirty
    assert edit.undo()
    restored = edit.save(tmp_path / "restored.nbt")
    assert load_root(restored) == before
    assert structure._root == before


def test_air_holes_and_structure_void_are_distinct(edit, tmp_path):
    assert edit.state_at((0, 1, 0)) is None
    assert edit.state_at((2, 0, 0)) == "minecraft:air"
    assert edit.state_at((3, 0, 0)) == "minecraft:structure_void"
    edit.apply(edit.set_block((0, 1, 0), "minecraft:air"))
    saved = Structure(edit.save(tmp_path / "air.nbt"))
    assert (0, 1, 0) in saved.present and (1, 1, 0) not in saved.present
    assert edit.undo()
    assert edit.state_at((0, 1, 0)) is None


def test_snapshot_records_are_detached_from_document_and_other_snapshots(edit):
    region = edit.select(((0, 0, 0), (2, 1, 1)))
    edit.apply(edit.move(region, (0, 1, 0), copy=True))
    snapshot = edit.snapshot()
    untouched = edit.snapshot()
    snapshot._block_records[(0, 1, 0)]["extra"] = StringTag("changed")
    snapshot.block_nbt[(1, 1, 0)]["Items"][0]["count"] = IntTag(99)
    snapshot.entities[0]["nbt"]["custom"] = StringTag("changed")
    for source in (untouched, edit.snapshot()):
        assert str(source._block_records[(0, 1, 0)]["extra"]) == "keep"
        assert int(source.block_nbt[(1, 1, 0)]["Items"][0]["count"]) == 3
        assert str(source.entities[0]["nbt"]["custom"]) == "keep"
    edit.undo()
    assert str(edit.snapshot()._block_records[(0, 0, 0)]["extra"]) == "keep"


def test_payload_removal_and_restoration(edit, tmp_path):
    chest = (1, 0, 0)
    properties = edit.set_block(chest, "minecraft:chest[facing=east]")
    assert properties.removed_block_entities == 0
    edit.apply(properties)
    assert chest in edit.snapshot().block_nbt
    change = edit.set_block(chest, "minecraft:stone")
    assert change.removed_block_entities == 1
    edit.apply(change)
    edit.apply(edit.set_block(chest, "minecraft:chest[facing=north]"))
    assert chest not in edit.snapshot().block_nbt
    edit.undo()
    edit.undo()
    assert chest in Structure(edit.save(tmp_path / "chest.nbt")).block_nbt


def test_multiple_palettes_survive_edits_and_undo(structure, tmp_path):
    root = deepcopy(structure._root)
    original = root.pop("palette")
    alternative = deepcopy(original)
    alternative[0] = parse_state("minecraft:dirt")
    root["palettes"] = ListTag([original, alternative])
    edit = EditSession.from_structure(Structure.from_root(root))
    edit.apply(edit.set_block((0, 0, 0), "minecraft:glass"))
    output = edit.save(tmp_path / "variants.nbt")
    assert Structure(output, palette_index=1).name_at((0, 0, 0)) == "minecraft:glass"
    assert edit.undo()
    assert load_root(edit.save(tmp_path / "restored.nbt")) == root


def test_stale_and_foreign_changes_fail_atomically(edit, structure):
    first = edit.set_block((0, 0, 0), "minecraft:glass")
    stale = edit.set_block((2, 0, 0), "minecraft:glass")
    edit.apply(first)
    edit.undo()
    with pytest.raises(StaleChangeError):
        edit.apply(stale)
    other = EditSession.from_structure(structure)
    with pytest.raises(StaleChangeError):
        other.apply(first)
    assert edit.state_at((2, 0, 0)) == "minecraft:air"


def test_invalid_later_delta_does_not_apply_earlier_delta(edit):
    change = edit.fill(edit.select(((0, 1, 0), (2, 2, 1))), "minecraft:glass")
    invalid = replace(change.changes[1], after=replace(change.changes[1].after, state="invalid state"))
    with pytest.raises(ValueError):
        edit.apply(replace(change, changes=(change.changes[0], invalid)))
    assert edit.revision == 0
    assert edit.state_at((0, 1, 0)) is None


def test_transaction_coalesces_and_rolls_back(edit):
    with pytest.raises(RuntimeError):
        with edit.transaction() as batch:
            batch.apply(batch.set_block((0, 0, 0), "minecraft:glass"))
            raise RuntimeError("Recipe failed")
    assert not edit.dirty
    with edit.transaction("Several operations") as batch:
        batch.apply(batch.set_block((0, 0, 0), "minecraft:glass"))
        batch.apply(batch.set_block((0, 0, 0), "minecraft:dirt"))
        batch.apply(batch.set_block((2, 0, 0), "minecraft:stone"))
    assert edit.undo()
    assert not edit.can_undo
    assert edit.state_at((0, 0, 0)) == "minecraft:stone"
    assert edit.state_at((2, 0, 0)) == "minecraft:air"
    assert edit.redo()
    assert edit.state_at((0, 0, 0)) == "minecraft:dirt"


def test_transaction_noop_does_not_create_history(edit):
    with edit.transaction() as batch:
        batch.apply(batch.set_block((0, 0, 0), "minecraft:glass"))
        batch.apply(batch.set_block((0, 0, 0), "minecraft:stone"))
    assert edit.revision == 0
    assert not edit.can_undo


def test_history_survives_cache_eviction_save_and_process_transfer(structure, tmp_path):
    import pickle

    edit = EditSession.from_structure(structure, history_cache_limit=2)
    for target in ("minecraft:glass", "minecraft:dirt", "minecraft:sand"):
        edit.apply(edit.set_block((0, 0, 0), target))
    edit.save(tmp_path / "history.nbt")
    edit = pickle.loads(pickle.dumps(edit))
    assert edit.undo() and edit.undo() and edit.undo() and not edit.undo()
    assert edit.state_at((0, 0, 0)) == "minecraft:stone"
    assert edit.redo() and edit.redo() and edit.redo() and not edit.redo()
    assert not edit.dirty
    assert edit.undo()
    edit.apply(edit.set_block((0, 0, 0), "minecraft:gold_block"))
    assert not edit.can_redo


def test_history_write_failure_preserves_document_and_redo(edit, monkeypatch):
    edit.apply(edit.set_block((0, 0, 0), "minecraft:glass"))
    edit.undo()
    change = edit.set_block((0, 0, 0), "minecraft:gold_block")
    revision = edit.revision
    def fail(*args, **kwargs):
        raise OSError("disk full")
    with monkeypatch.context() as patch:
        patch.setattr("structura_edit.history.sqlite3.connect", fail)
        with pytest.raises(OSError, match="disk full"):
            edit.apply(change)
    assert edit.revision == revision and not edit.dirty
    assert edit.state_at((0, 0, 0)) == "minecraft:stone"
    assert edit.redo() and edit.state_at((0, 0, 0)) == "minecraft:glass"


def test_limits_and_bounds(edit, structure):
    for bounds in (((0, 0, 0), (0, 1, 1)), ((-1, 0, 0), (1, 1, 1)), ((0, 0, 0), (5, 1, 1))):
        with pytest.raises(ValueError):
            edit.select(bounds)
    with pytest.raises(ValueError):
        Selection((True, 0, 0), (1, 1, 1))
    small = EditSession.from_structure(structure, operation_limit=3)
    with pytest.raises(ValueError):
        small.fill(small.select(), "minecraft:stone")
    assert not small.dirty


def test_matching_does_not_copy_incompatible_properties(edit):
    assert len(edit.replace(edit.select(), "minecraft:chest", "minecraft:stone")) == 1
    assert len(edit.replace(edit.select(), "minecraft:chest", "minecraft:stone", exact=True)) == 0
    assert len(edit.replace(edit.select(), "minecraft:chest[facing=south]", "minecraft:stone")) == 0
    edit.apply(edit.replace(edit.select(), "minecraft:chest", "minecraft:stone"))
    assert edit.state_at((1, 0, 0)) == "minecraft:stone"


def test_randomized_undo_redo_matches_cell_oracle(edit):
    rng = random.Random(104)
    initial = {p: edit.state_at(p) for p in edit.select().positions()}
    states = [initial]
    cursor = 0
    for _ in range(180):
        action = rng.randrange(4)
        if action == 0 and cursor:
            assert edit.undo()
            cursor -= 1
        elif action == 1 and cursor + 1 < len(states):
            assert edit.redo()
            cursor += 1
        else:
            pos = (rng.randrange(4), rng.randrange(2), rng.randrange(3))
            target = rng.choice(("minecraft:air", "minecraft:stone", "minecraft:glass"))
            change = edit.set_block(pos, target)
            if change:
                expected = states[cursor].copy()
                expected[pos] = target
                states[cursor + 1:] = [expected]
                cursor += 1
                edit.apply(change)
        assert {p: edit.state_at(p) for p in initial} == states[cursor]
        counts = Counter(state for state in states[cursor].values() if state is not None)
        assert edit.palette_counts() == counts
        assert edit.palette_counts(edit.select()) == counts
        assert edit.palette_counts(by_state=False) == Counter(
            state.split("[", 1)[0] for state in states[cursor].values() if state is not None)
        selected = edit.select(((0, 0, 0), (2, 1, 2)))
        assert edit.palette_counts(selected) == Counter(
            state for position, state in states[cursor].items() if position in selected and state is not None)


def test_replace_material_retains_only_compatible_properties(edit):
    edit.apply(edit.set_block((0, 0, 0), "minecraft:oak_stairs[facing=east,half=top,shape=straight,waterlogged=true]"))
    change = edit.replace(edit.select(), "minecraft:oak_stairs", "minecraft:spruce_stairs[half=bottom]", preserve_properties=True)
    edit.apply(change)
    assert edit.state_at((0, 0, 0)) == "minecraft:spruce_stairs[facing=east,half=bottom,shape=straight,waterlogged=true]"
    edit.apply(edit.replace(edit.select(), "minecraft:spruce_stairs", "minecraft:stone", preserve_properties=True))
    assert edit.state_at((0, 0, 0)) == "minecraft:stone"


def test_failed_save_keeps_dirty_and_previous_file(edit, tmp_path, monkeypatch):
    from structura_core import nbt_io

    path = edit.save(tmp_path / "original.nbt")
    original = path.read_bytes()
    edit.apply(edit.set_block((0, 0, 0), "minecraft:glass"))

    def fail_replace(*args):
        raise OSError("interrupted write")

    monkeypatch.setattr(nbt_io.os, "replace", fail_replace)
    with pytest.raises(OSError, match="interrupted write"):
        edit.save(path)
    assert path.read_bytes() == original and edit.dirty
    assert edit.undo() and not edit.dirty


def test_headless_import_does_not_load_gui():
    result = subprocess.run([sys.executable, "-c", "import sys, structura_edit; assert not any(k.startswith(('PySide6', 'pyvista', 'structura_render')) for k in sys.modules)"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
