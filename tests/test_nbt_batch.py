from copy import deepcopy
from dataclasses import replace

import pytest
from amulet_nbt import ByteTag, IntTag, ShortTag, StringTag, from_snbt
from structura_core import Structure

from nbt_batch_fixture import batch_structure
from structura_edit import CellSet, EditSession, StaleChangeError, collect_nbt_targets, replace_nbt_values
from structura_edit.nbt_batch import parse_field_path
from structura_edit.tasks import execute


def test_batch_covers_all_pages_preserves_data_and_undo(tmp_path):
    source = batch_structure()
    before = deepcopy(source._root)
    session = EditSession.from_structure(source)
    targets = collect_nbt_targets(session, 'chest')
    plan = replace_nbt_values(session, targets, '/Items/0/count', '7')
    assert plan.total == len(plan.change) == 150 and not plan.skipped and plan.unchanged == 0
    assert len(plan.samples) == 24 and not session.dirty
    assert session.apply(plan.change) == 150 and session.history.cursor == 1
    saved = Structure(session.save(tmp_path / 'batch.nbt'))
    for payload in saved.block_nbt.values():
        assert payload['Items'][0]['count'] == ByteTag(7)
        assert payload['custom'] == from_snbt('42L')
    assert saved.entities == source.entities
    assert all(record['extra'] == from_snbt('{keep:42L}') for record in saved._block_records.values())
    assert source._root == before
    assert session.undo()
    assert session.snapshot().block_nbt == source.block_nbt
    assert session.redo() and not session.dirty


def test_each_object_keeps_its_type_and_invalid_values_are_reported():
    source = batch_structure(3)
    source.block_nbt[(1, 0, 0)]['Items'][0]['count'] = ShortTag(3)
    source.block_nbt[(2, 0, 0)]['Items'][0]['count'] = IntTag(3)
    session = EditSession.from_structure(source)
    plan = replace_nbt_values(session, collect_nbt_targets(session), ('Items', 0, 'count'), '128')
    assert len(plan.change) == 2 and sum(count for reason, count in plan.skipped) == 1
    session.apply(plan.change)
    counts = [session.snapshot().block_nbt[(x, 0, 0)]['Items'][0]['count'] for x in range(3)]
    assert counts == [ByteTag(3), ShortTag(128), IntTag(128)]
    assert [type(value) for value in counts] == [ByteTag, ShortTag, IntTag]


def test_sparse_selection_excludes_holes_in_search_and_batch():
    session = EditSession.from_structure(batch_structure(3))
    selection = CellSet.from_positions(((0, 0, 0), (2, 0, 0)))
    assert session.find_objects(selection=selection).total == 2
    targets = collect_nbt_targets(session, selection=selection)
    assert len(targets.rows) == 2
    session.apply(replace_nbt_values(session, targets, '/custom', '100').change)
    assert int(session.snapshot().block_nbt[(1, 0, 0)]['custom']) == 42


def test_entity_batch_preserves_uuid_position_and_other_fields():
    session = EditSession.from_structure(batch_structure(3))
    before = session.snapshot().entities
    plan = replace_nbt_values(session, collect_nbt_targets(session, 'pig', kind='entities'), '/CustomName', 'New name')
    assert len(plan.change.entities) == 2 and not plan.change.resize
    session.apply(plan.change)
    for old, new in zip(before, session.snapshot().entities):
        assert new['nbt']['CustomName'] == StringTag('New name')
        assert new['nbt']['UUID'] == old['nbt']['UUID'] and new['pos'] == old['pos']
    session.undo()
    assert session.snapshot().entities == before


@pytest.mark.parametrize('path,text,reason', [('/missing', '1', 'Field is missing'),
                                           ('/Items/99/count', '1', 'List or array index is missing'),
                                           ('/custom/nested', '1', 'Field path crosses a scalar'),
                                           ('/Items', '1', 'Field is not a scalar'),
                                           ('/custom', '1.5', 'Enter a whole number')])
def test_skips_are_explicit_and_preview_does_not_mutate(path, text, reason):
    session = EditSession.from_structure(batch_structure(3))
    plan = replace_nbt_values(session, collect_nbt_targets(session), path, text)
    assert not plan.change and plan.skipped == ((reason, 3),)
    assert not session.dirty and not session.can_undo


def test_unchanged_values_create_no_history_and_stale_targets_are_rejected():
    session = EditSession.from_structure(batch_structure(3))
    targets = collect_nbt_targets(session)
    plan = replace_nbt_values(session, targets, '/custom', '42')
    assert plan.unchanged == 3 and not plan.change
    session.apply(plan.change)
    assert not session.can_undo
    session.apply(session.set_block((0, 0, 0), 'minecraft:stone'))
    session.undo()
    with pytest.raises(StaleChangeError):
        replace_nbt_values(session, targets, '/custom', '43')


def test_array_and_escaped_keys_are_supported():
    source = batch_structure(3)
    for payload in source.block_nbt.values():
        payload['a/b~c'] = from_snbt('{"0":[I;1,2,3]}')
    session = EditSession.from_structure(source)
    plan = replace_nbt_values(session, collect_nbt_targets(session), '/a~1b~0c/0/1', '99')
    session.apply(plan.change)
    assert all(int(payload['a/b~c']['0'][1]) == 99 for payload in session.snapshot().block_nbt.values())


@pytest.mark.parametrize('path', ['', 'Items/0/count', '/bad~2', '/bad~', '/' * 130])
def test_invalid_path_is_rejected(path):
    with pytest.raises(ValueError):
        parse_field_path(path)


@pytest.mark.parametrize('path', ['/id', '/UUID/0', '/Pos/0', '/x'])
def test_batch_cannot_reassign_identity_or_move_objects(path):
    session = EditSession.from_structure(batch_structure(3))
    with pytest.raises(ValueError, match='Identity and position'):
        replace_nbt_values(session, collect_nbt_targets(session), path, '1')
    assert not session.dirty


def test_budget_and_duplicate_targets_fail_without_partial_changes(monkeypatch):
    session = EditSession.from_structure(batch_structure(3))
    targets = collect_nbt_targets(session)
    with pytest.raises(ValueError, match='duplicates'):
        replace_nbt_values(session, replace(targets, rows=(*targets.rows, targets.rows[0])), '/custom', '43')
    monkeypatch.setattr('structura_edit.nbt_batch.MAX_BATCH_OBJECTS', 2)
    with pytest.raises(ValueError, match='narrow'):
        collect_nbt_targets(session)
    assert not session.dirty


def test_worker_plan_has_shared_change_report_and_respects_readonly():
    session = EditSession.from_structure(batch_structure(3))
    targets = execute('nbt_targets', {'session': session, 'query': {'text': 'chest'}})
    plan = execute('nbt_batch', {'session': session, 'targets': targets, 'path': '/custom', 'text': '50'})
    assert plan.change.report.block_data == 3
    session._document.readonly = True
    with pytest.raises(ValueError, match='view-only'):
        replace_nbt_values(session, targets, '/custom', '50')
