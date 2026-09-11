import pickle
from dataclasses import replace
from threading import Event, current_thread

import pytest

from structura_edit.changes import StaleChangeError
from structura_edit.jobs import Worker
from structura_edit.object_edits import edit_block_data, transform_entities
from structura_edit.object_search import ObjectSearch
from structura_edit.session import EditSession
from structura_edit.task_protocol import ApplyCommand, DocumentRequest, HistoryCommand, ObjectSearchCommand, SaveCommand, TaskSuccess
from structura_edit.worker_delta import DocumentDelta
from structura_edit.worker_document import WorkerDocument, document_token
from test_jobs import wait, wait_stopped


def transfer(value):
    return pickle.loads(pickle.dumps(value))


def assert_snapshot(actual, expected):
    assert (actual._id, actual.revision, actual._state_id, actual._transition) == (expected._id, expected.revision, expected._state_id, expected._transition)
    assert actual._cells == expected._cells
    assert actual._entities == expected._entities
    assert actual.history.entries == expected.history.entries
    assert actual.history.cursor == expected.history.cursor
    assert actual.dirty == expected.dirty
    assert actual._saved_changes == expected._saved_changes
    if hasattr(actual, 'world_changes'):
        assert actual.world_changes.patch == expected.world_changes.patch
        assert actual.world_changes.entities == expected.world_changes.entities
        assert actual.world_changes.history is actual.history
    left, right = actual.snapshot(), expected.snapshot()
    assert (left.present, left.block_nbt, left.entities) == (right.present, right.block_nbt, right.entities)


@pytest.mark.parametrize('fixture', ['edit', 'world_edit'])
def test_compact_apply_undo_redo_nbt_and_branch_match_worker_snapshot(request, fixture):
    current = request.getfixturevalue(fixture)
    current.history.prepare()
    slot = WorkerDocument()
    token = document_token(current)
    previous = []
    commands = [lambda s: ApplyCommand(s.set_block((0, 0, 0), 'minecraft:glass')),
                lambda s: ApplyCommand(edit_block_data(s, (1, 0, 0), '{id:"minecraft:chest",custom:7}')),
                lambda s: HistoryCommand(1), lambda s: HistoryCommand(2), lambda s: HistoryCommand(1),
                lambda s: ApplyCommand(s.set_block((0, 0, 0), 'minecraft:gold_block')),
                lambda s: HistoryCommand(1), lambda s: HistoryCommand(2),
                lambda s: ApplyCommand(s.set_block((0, 0, 0), 'minecraft:gold_block'))]
    for build in commands:
        before = transfer(current)
        command = build(current)
        delta, version = slot.execute(DocumentRequest(token, command, transfer(current) if slot.session is None else None))
        delta = transfer(delta)
        assert isinstance(delta, DocumentDelta)
        previous.append((current, before))
        current = delta.restore(current, token, version)
        token = version
        assert_snapshot(current, slot.session)
        for old, frozen in previous:
            assert_snapshot(old, frozen)
        assert current.history is not slot.session.history
    current._cells.clear()
    if hasattr(current, 'world_changes'):
        current.world_changes.patch.clear()
    for old, frozen in previous:
        assert_snapshot(old, frozen)


def test_delta_rejects_different_base_and_preserves_source(edit):
    slot = WorkerDocument()
    token = document_token(edit)
    delta, version = slot.execute(DocumentRequest(token, ApplyCommand(edit.set_block((0, 0, 0), 'minecraft:glass')), transfer(edit)))
    for base, target in ((replace(token, snapshot_id='other'), version), (token, None),
                         (token, replace(version, revision=version.revision + 2))):
        with pytest.raises(StaleChangeError):
            delta.restore(edit, base, target)
    edit.apply(edit.set_block((0, 0, 0), 'minecraft:gold_block'))
    with pytest.raises(StaleChangeError):
        delta.restore(edit, token, version)
    assert edit.state_at((0, 0, 0)) == 'minecraft:gold_block'


def test_resize_entities_save_and_multi_step_history_keep_full_snapshot(edit, tmp_path):
    for state in ('minecraft:glass', 'minecraft:gold_block'):
        edit.apply(edit.set_block((0, 0, 0), state))
    commands = [HistoryCommand(0), SaveCommand(str(tmp_path / 'saved.nbt')),
                ApplyCommand(transform_entities(edit, list(edit._entities), offset=(1, 0, 0))),
                ApplyCommand(edit.paste(edit.copy(edit.select(((0, 0, 0), (1, 1, 1)))), (5, 0, 0)))]
    for command in commands:
        slot = WorkerDocument()
        result, _ = slot.execute(DocumentRequest(document_token(edit), command, transfer(edit)))
        assert isinstance(result, EditSession)


def test_cancel_while_restoring_delta_discards_reply_and_waits_for_thread(edit, monkeypatch):
    entered, release = Event(), Event()
    restore = DocumentDelta.restore
    def delayed(delta, *args):
        assert current_thread().name == 'worker-exchange'
        entered.set()
        assert release.wait(5)
        return restore(delta, *args)
    monkeypatch.setattr(DocumentDelta, 'restore', delayed)
    worker = Worker()
    try:
        worker.submit_document(ApplyCommand(edit.set_block((0, 0, 0), 'minecraft:glass')), edit)
        assert entered.wait(10)
        worker.close()
        assert worker.stopping and not edit.dirty and not edit.can_undo
        release.set()
        wait_stopped(worker)
        assert worker.poll() is None
        worker.submit_document(ObjectSearchCommand(), edit)
        assert isinstance(wait(worker), TaskSuccess)
        assert not edit.dirty
    finally:
        release.set()
        worker.close()
        wait_stopped(worker)


def test_search_snapshot_replacement_invalidates_index_even_with_same_revision(edit):
    search = ObjectSearch()
    slot = WorkerDocument()
    first, _ = slot.execute(DocumentRequest(document_token(edit), ObjectSearchCommand(), transfer(edit)), object_search=search)
    changed = transfer(edit)
    changed._document.source.present.pop((0, 0, 0))
    second, _ = slot.execute(DocumentRequest(document_token(changed), ObjectSearchCommand(), changed), object_search=search)
    assert second.total == first.total - 1


def test_world_history_delta_in_other_dimension_leaves_loaded_cells_intact(world_edit):
    from structura_edit.changes import ChangeSet, _Cell, _Delta

    world_edit._document.origin = (-32, -64, -32)
    key = ('minecraft:the_nether', -320, -60, -320)
    world_edit.world_changes.apply(ChangeSet(world_edit._id, world_edit.revision, 'Remote block',
                                             (_Delta(key, _Cell('minecraft:air'), _Cell('minecraft:glass')),)))
    world_edit._sync_changes()
    slot = WorkerDocument()
    token = document_token(world_edit)
    delta, version = slot.execute(DocumentRequest(token, HistoryCommand(0), transfer(world_edit)))
    assert isinstance(delta, DocumentDelta) and not delta.cells
    current = transfer(delta).restore(world_edit, token, version)
    assert key not in current.world_changes.patch and key in world_edit.world_changes.patch
    assert_snapshot(current, slot.session)
    delta, token = slot.execute(DocumentRequest(version, HistoryCommand(1)))
    restored = transfer(delta).restore(current, version, token)
    assert key in restored.world_changes.patch
    assert_snapshot(restored, slot.session)


def test_failed_delta_restoration_preserves_redo_and_retry_uses_fresh_snapshot(edit, monkeypatch):
    edit.apply(edit.set_block((0, 0, 0), 'minecraft:gold_block'))
    edit.undo()
    original = transfer(edit)
    restore = DocumentDelta.restore
    def failed(*args):
        raise OSError('Snapshot reconstruction failed')
    monkeypatch.setattr(DocumentDelta, 'restore', failed)
    worker = Worker()
    try:
        from structura_edit.task_protocol import TaskFailure

        worker.submit_document(ApplyCommand(edit.set_block((0, 0, 0), 'minecraft:glass')), edit)
        reply = wait(worker)
        assert isinstance(reply, TaskFailure) and worker._resident is None
        assert not edit.dirty and edit.history.cursor == 0
        assert original.redo() and original.state_at((0, 0, 0)) == 'minecraft:gold_block'
        monkeypatch.setattr(DocumentDelta, 'restore', restore)
        worker.submit_document(ApplyCommand(edit.set_block((0, 0, 0), 'minecraft:glass')), edit)
        reply = wait(worker)
        assert isinstance(reply, TaskSuccess)
        assert reply.payload.state_at((0, 0, 0)) == 'minecraft:glass'
        assert len(reply.payload.history.entries) == 1
    finally:
        worker.close()
        wait_stopped(worker)
