from copy import copy, deepcopy
from dataclasses import replace
from random import Random
from types import SimpleNamespace

import pytest
from structura_core.world import WorldRegion

from structura_edit.changes import StaleChangeError, _Cell
from structura_edit.object_edits import edit_block_data, transform_entities
from structura_edit.sections import changed_positions
from structura_edit.world_view import WorldView


def view_at(structure, path, origin=(0, 0, 0), dimension='minecraft:overworld', changes=None):
    source = deepcopy(structure)
    source.source_origin = origin
    region = WorldRegion(source, frozenset({(origin[0] // 16, origin[2] // 16)}), frozenset(), (),
                         dimension, origin, 0, 16)
    world = SimpleNamespace(path=path, dimensions={dimension: path}, name='Delta test')
    return WorldView(world, region, changes)


def assert_full_sync(view):
    reference = copy(view)
    reference._sync_changes()
    assert view._cells == reference._cells
    assert view._entities == reference._entities
    assert (view._id, view.revision, view._state_id) == (reference._id, reference.revision, reference._state_id)
    assert view.snapshot().block_nbt == reference.snapshot().block_nbt


def state(view):
    changes = view.world_changes
    return (changes.patch.copy(), changes.entities.copy(), changes.state_id, changes.revision,
            tuple(view.history.entries), view.history.cursor, view._cells.copy(), view._entities.copy(),
            view.revision, view._state_id, view._transition)


class NoScan(dict):
    def fail(self, *args, **kwargs):
        pytest.fail('A one-block change scanned the accumulated world patch')

    copy = items = keys = values = __iter__ = fail


def test_one_block_apply_undo_redo_do_not_scan_or_replace_accumulated_maps(world_edit, monkeypatch):
    view = world_edit
    patch = view.world_changes.patch = NoScan({(view.dimension, 32 + x, 0, 0): (_Cell('minecraft:stone'), _Cell('minecraft:air'))
                                             for x in range(1000)})
    entities = view.world_changes.entities = NoScan()
    cells, visible = view._cells, view._entities
    monkeypatch.setattr(view, '_sync_changes', lambda: pytest.fail('Full synchronization during one-block edit'))
    monkeypatch.setattr('structura_edit.world_view.visible_entities', lambda view: pytest.fail('Unchanged entities were rebuilt'))
    assert view.apply(view.set_block((0, 0, 0), 'minecraft:glass')) == 1
    assert view.undo() and view.redo()
    assert view.world_changes.patch is patch and view.world_changes.entities is entities
    assert view._cells is cells and view._entities is visible
    assert view.state_at((0, 0, 0)) == 'minecraft:glass' and len(patch) == 1001


def test_history_write_failure_preserves_world_patch_visible_state_and_redo(world_edit, monkeypatch):
    import sqlite3

    view = world_edit
    view.apply(view.set_block((0, 0, 0), 'minecraft:glass'))
    view.undo()
    before = state(view)
    def failed(*args, **kwargs):
        raise sqlite3.OperationalError('disk full')
    with monkeypatch.context() as patch:
        patch.setattr('structura_edit.history.sqlite3.connect', failed)
        with pytest.raises(sqlite3.OperationalError):
            view.apply(view.set_block((0, 0, 0), 'minecraft:gold_block'))
    assert state(view) == before
    assert view.redo() and view.state_at((0, 0, 0)) == 'minecraft:glass'


def test_pending_budget_uses_net_block_and_entity_growth_before_mutation(world_edit, monkeypatch):
    view = world_edit
    monkeypatch.setattr('structura_edit.world_changes.MAX_PENDING_BLOCKS', 1)
    view.apply(view.set_block((0, 0, 0), 'minecraft:glass'))
    view.apply(view.set_block((0, 0, 0), 'minecraft:gold_block'))
    before = state(view)
    with pytest.raises(ValueError, match='Pending world changes'):
        view.apply(view.set_block((2, 0, 0), 'minecraft:glass'))
    assert state(view) == before
    duplicate = transform_entities(view, view._entities, action='Duplicate')
    change = replace(view.set_block((0, 0, 0), 'minecraft:stone'), entities=duplicate.entities)
    view.apply(change)
    assert not view.world_changes.patch and len(view.world_changes.entities) == 1
    assert_full_sync(view)
    assert view.undo() and len(view.world_changes.patch) == 1 and not view.world_changes.entities
    assert_full_sync(view)


def test_failed_history_read_preserves_world_and_cursor(world_edit, monkeypatch):
    view = world_edit
    view.apply(view.set_block((0, 0, 0), 'minecraft:glass'))
    before = state(view)
    def failed(index):
        raise OSError('History unavailable')
    monkeypatch.setattr(view.history, 'get', failed)
    with pytest.raises(OSError):
        view.undo()
    assert state(view) == before


def test_fork_and_serialized_snapshot_stay_independent_and_keep_transition(world_edit):
    import pickle

    view = world_edit
    before = view.fork()
    view.apply(view.set_block((0, 0, 0), 'minecraft:glass'))
    published = pickle.loads(pickle.dumps(view, protocol=5))
    branch = view.fork()
    assert tuple(changed_positions(before, branch)) == ((0, 0, 0),)
    branch.apply(branch.set_block((0, 0, 0), 'minecraft:gold_block'))
    assert view.state_at((0, 0, 0)) == published.state_at((0, 0, 0)) == 'minecraft:glass'
    assert before.state_at((0, 0, 0)) == 'minecraft:stone'
    assert view.undo() and published.state_at((0, 0, 0)) == 'minecraft:glass'
    assert branch.state_at((0, 0, 0)) == 'minecraft:gold_block'


def test_stale_view_cannot_apply_and_history_resynchronizes_shared_world(world_edit):
    view = world_edit
    older = copy(view)
    older._sync_changes()
    stale = older.set_block((2, 0, 0), 'minecraft:gold_block')
    view.apply(view.set_block((0, 0, 0), 'minecraft:glass'))
    before = state(view)
    with pytest.raises(StaleChangeError):
        older.apply(stale)
    assert state(view) == before
    assert older.undo() and older.state_at((0, 0, 0)) == 'minecraft:stone'
    assert_full_sync(older)


@pytest.mark.parametrize('origin', [(0, 0, 0), (-16, -32, -16)])
def test_local_updates_match_full_sync_through_nbt_entities_and_saved_baseline(structure, tmp_path, monkeypatch, origin):
    view = view_at(structure, tmp_path, origin)
    view.apply(edit_block_data(view, (1, 0, 0), '{id:"minecraft:chest",Items:[{Slot:0b,id:"mod:gem",count:9}]}'))
    view.apply(transform_entities(view, view._entities, action='Move', offset=(1, 0, 0)))
    assert_full_sync(view)
    monkeypatch.setattr('structura_core.world_write.save_world_patch', lambda *args, **kwargs: None)
    view.save()
    assert not view.dirty
    for action in (view.undo, view.undo, view.redo, view.redo):
        assert action()
        assert_full_sync(view)
    assert not view.dirty


def reference_update(patch, deltas, reverse=False, entities=False):
    result = patch.copy()
    for delta in deltas:
        before, after = (delta.after, delta.before) if reverse else (delta.before, delta.after)
        key = delta.key if entities else delta.position
        baseline = result[key][0] if key in result else before
        if baseline == after:
            result.pop(key, None)
        else:
            result[key] = baseline, after
    return result


@pytest.mark.parametrize('seed', [1, 7, 29])
def test_edit_history_reload_sequences_match_copying_reference(structure, tmp_path, seed):
    random = Random(seed)
    view = view_at(structure, tmp_path)
    for _ in range(80):
        blocks, entities = view.world_changes.patch.copy(), view.world_changes.entities.copy()
        action = random.choice(('edit', 'edit', 'nbt', 'entity', 'undo', 'redo', 'reload'))
        change, reverse = None, False
        if action == 'reload':
            view = view_at(structure, tmp_path, random.choice(((0, 0, 0), (-16, -32, -16), (32, 0, 0))),
                           random.choice(('minecraft:overworld', 'minecraft:the_nether')), view.world_changes)
        elif action in ('undo', 'redo'):
            index = view.history.cursor - 1 if action == 'undo' else view.history.cursor
            if 0 <= index < len(view.history.entries):
                change = view.history.get(index)[1]
                reverse = action == 'undo'
            assert getattr(view, action)() == (change is not None)
        else:
            if action == 'nbt':
                planned = edit_block_data(view, (1, 0, 0), '{id:"minecraft:chest",value:' + str(random.randrange(5)) + '}')
            elif action == 'entity' and view._entities:
                planned = transform_entities(view, view._entities, action='Rotate', angle=90)
            else:
                planned = view.set_block((random.choice((0, 2)), 0, 0), random.choice(('minecraft:stone', 'minecraft:air', 'minecraft:glass')))
            if view.apply(planned):
                change = view.history.get(view.history.cursor - 1)[1]
        if change is not None:
            blocks = reference_update(blocks, change.changes, reverse)
            entities = reference_update(entities, change.entities, reverse, True)
        assert view.world_changes.patch == blocks and view.world_changes.entities == entities
        assert_full_sync(view)
