from copy import deepcopy
from dataclasses import replace
import pickle
from threading import Event

import pytest

from structura_edit.changes import StaleChangeError
from structura_edit.jobs import Worker
from structura_edit.task_protocol import (
    ApplyCommand, DocumentRequest, HistoryCommand, OperationCommand, RecipeCommand, SaveCommand,
    TaskFailure, TaskSuccess,
)
from structura_edit.worker_document import WorkerDocument, document_token
from test_jobs import wait, wait_stopped


def fill(session, target='minecraft:glass'):
    return OperationCommand('Fill', session.select(((0, 0, 0), (1, 1, 1))), {'target': target})


def test_document_slot_rejects_unknown_and_stale_versions(edit):
    slot = WorkerDocument()
    token = document_token(edit)
    request = DocumentRequest(token, fill(edit))
    with pytest.raises(StaleChangeError):
        slot.execute(request)
    change, received = slot.execute(replace(request, snapshot=deepcopy(edit)))
    assert received == token and len(change) == 1
    for token in (replace(token, revision=1), replace(token, snapshot_id='different'), replace(token, document_id='different')):
        with pytest.raises(StaleChangeError):
            slot.execute(replace(request, token=token))
    assert not edit.dirty


def test_recipe_failure_evicts_state_and_next_snapshot_recovers(edit):
    slot = WorkerDocument()
    token = document_token(edit)
    command = RecipeCommand('edit.apply(edit.fill(selection, "minecraft:glass"))\nraise ValueError("broken")', edit.select())
    with pytest.raises(ValueError, match='broken'):
        slot.execute(DocumentRequest(token, command, deepcopy(edit)))
    assert slot.session is None and slot.token is None and not edit.dirty
    change, _ = slot.execute(DocumentRequest(token, fill(edit), deepcopy(edit)))
    assert len(change) == 1


def test_one_slot_replaces_same_revision_but_different_loaded_snapshot(edit):
    slot = WorkerDocument()
    first = document_token(edit)
    slot.execute(DocumentRequest(first, fill(edit), deepcopy(edit)))
    refreshed = deepcopy(edit)
    refreshed._document.source.present.pop((0, 0, 0))
    second = document_token(refreshed)
    change, _ = slot.execute(DocumentRequest(second, fill(refreshed), refreshed))
    assert change.changes[0].before is None
    with pytest.raises(StaleChangeError):
        slot.execute(DocumentRequest(first, fill(edit)))


def test_real_worker_reuses_document_and_updates_version_after_apply_history_save(edit, tmp_path):
    edit.history.prepare()
    worker = Worker()
    try:
        worker.submit_document(fill(edit), edit)
        first = wait(worker)
        assert isinstance(first, TaskSuccess), first
        token = first.document
        assert token is not None and not edit.dirty
        worker.submit_document(fill(edit), edit)
        second = wait(worker)
        assert isinstance(second, TaskSuccess) and second.document == token
        assert second.payload == first.payload
        worker.submit_document(ApplyCommand(first.payload), edit)
        applied = wait(worker)
        assert isinstance(applied, TaskSuccess), applied
        current = applied.payload
        assert current.state_at((0, 0, 0)) == 'minecraft:glass' and not edit.dirty
        assert applied.document != token and worker._resident[0] is current
        for index, expected in ((0, 'minecraft:stone'), (1, 'minecraft:glass')):
            worker.submit_document(HistoryCommand(index), current)
            reply = wait(worker)
            assert isinstance(reply, TaskSuccess), reply
            current = reply.payload
            assert current.state_at((0, 0, 0)) == expected
        worker.submit_document(SaveCommand(str(tmp_path / 'saved.nbt')), current)
        saved = wait(worker)
        assert isinstance(saved, TaskSuccess), saved
        assert not saved.payload.dirty and saved.payload.can_undo
        assert worker._resident[0] is saved.payload
        worker.submit_document(fill(saved.payload, 'minecraft:gold_block'), saved.payload)
        reply = wait(worker)
        assert isinstance(reply, TaskSuccess) and reply.document == saved.document
    finally:
        worker.close()
        wait_stopped(worker)


def test_failed_command_clears_acknowledgement_without_automatic_retry(edit):
    worker = Worker()
    try:
        worker.submit_document(fill(edit), edit)
        assert isinstance(wait(worker), TaskSuccess)
        worker.submit_document(HistoryCommand(-1), edit)
        failure = wait(worker)
        assert isinstance(failure, TaskFailure) and worker._resident is None
        assert not worker.busy and worker.poll() is None
        worker.submit_document(fill(edit), edit)
        assert isinstance(wait(worker), TaskSuccess)
    finally:
        worker.close()
        wait_stopped(worker)


def test_worker_death_requires_new_snapshot_and_does_not_repeat_the_command(edit):
    worker = Worker()
    try:
        worker.submit_document(fill(edit), edit)
        assert isinstance(wait(worker), TaskSuccess)
        worker.submit_document(RecipeCommand('while True: pass', edit.select()), edit)
        worker._process.terminate()
        worker._process.join(timeout=3)
        failure = wait(worker)
        assert isinstance(failure, TaskFailure) and not worker.busy and worker._resident is None
        assert worker.poll() is None and not edit.dirty
        worker.submit_document(fill(edit), edit)
        assert isinstance(wait(worker), TaskSuccess)
    finally:
        worker.close()
        wait_stopped(worker)


def test_cancel_during_preparation_bounds_threads_and_discards_old_payload(edit):
    worker = Worker()
    entered, release = Event(), Event()
    def prepare():
        entered.set()
        assert release.wait(5)
        return {'session': edit, 'selection': edit.select(), 'code': 'raise RuntimeError("must not run")'}
    try:
        worker.submit('recipe', prepare_args=prepare)
        assert entered.wait(5)
        worker.close()
        assert worker.stopping and worker.busy
        with pytest.raises(RuntimeError, match='stopping'):
            worker.submit('open')
        release.set()
        wait_stopped(worker)
        assert worker.poll() is None
        worker.submit_document(fill(edit), edit)
        assert isinstance(wait(worker), TaskSuccess)
    finally:
        release.set()
        worker.close()
        wait_stopped(worker)


def test_document_reference_serialization_does_not_include_the_snapshot(edit):
    token = document_token(edit)
    cold = DocumentRequest(token, fill(edit), edit)
    warm = replace(cold, snapshot=None)
    assert len(pickle.dumps(warm)) < len(pickle.dumps(cold))
    assert pickle.loads(pickle.dumps(warm)) == warm


def test_lost_apply_reply_preserves_original_redo_in_shared_sqlite(edit):
    edit.apply(edit.set_block((0, 0, 0), 'minecraft:gold_block'))
    edit.undo()
    original = pickle.loads(pickle.dumps(edit))
    slot = WorkerDocument()
    request = DocumentRequest(document_token(edit), ApplyCommand(edit.set_block((0, 0, 0), 'minecraft:glass')),
                              pickle.loads(pickle.dumps(edit)))
    delta, token = slot.execute(request)
    applied = delta.restore(edit, request.token, token)
    assert applied.state_at((0, 0, 0)) == 'minecraft:glass'
    slot.clear()
    assert original.redo() and original.state_at((0, 0, 0)) == 'minecraft:gold_block'


def test_confirmed_document_prunes_discarded_rows_on_next_command(edit):
    import sqlite3

    edit.apply(edit.set_block((0, 0, 0), 'minecraft:gold_block'))
    edit.undo()
    slot = WorkerDocument()
    delta, token = slot.execute(DocumentRequest(document_token(edit), ApplyCommand(edit.set_block((0, 0, 0), 'minecraft:glass')),
                                                pickle.loads(pickle.dumps(edit))))
    result = delta.restore(edit, delta.base, token)
    with sqlite3.connect(result.history.path) as db:
        assert db.execute('SELECT COUNT(*) FROM changes').fetchone()[0] == 2
    slot.execute(DocumentRequest(token, fill(result)))
    with sqlite3.connect(result.history.path) as db:
        assert db.execute('SELECT COUNT(*) FROM changes').fetchone()[0] == 1
    assert not slot.session.history._pending_prune


def test_partial_history_failure_evicts_worker_state_and_preserves_gui_snapshot(edit, monkeypatch):
    for state in ('minecraft:gold_block', 'minecraft:glass'):
        edit.apply(edit.set_block((0, 0, 0), state))
    original = pickle.loads(pickle.dumps(edit))
    slot = WorkerDocument()
    slot.execute(DocumentRequest(document_token(edit), fill(edit), pickle.loads(pickle.dumps(edit))))
    get = slot.session.history.get
    def failing(index):
        if index == 0:
            raise OSError('Second history entry unavailable')
        return get(index)
    monkeypatch.setattr(slot.session.history, 'get', failing)
    with pytest.raises(OSError, match='Second history'):
        slot.execute(DocumentRequest(slot.token, HistoryCommand(0)))
    assert slot.session is None and slot.token is None
    assert original.history.cursor == 2 and original.state_at((0, 0, 0)) == 'minecraft:glass'
    assert original.undo() and original.state_at((0, 0, 0)) == 'minecraft:gold_block'


def test_failed_save_after_file_write_keeps_gui_dirty_and_is_not_replayed(edit, tmp_path, monkeypatch):
    edit.apply(edit.set_block((0, 0, 0), 'minecraft:glass'))
    slot = WorkerDocument()
    slot.execute(DocumentRequest(document_token(edit), fill(edit), pickle.loads(pickle.dumps(edit))))
    saved = slot.session.save
    calls = []
    path = tmp_path / 'written.nbt'
    def fail_after_save(*args, **kwargs):
        calls.append(args)
        saved(*args, **kwargs)
        raise OSError('Reply could not be prepared')
    monkeypatch.setattr(slot.session, 'save', fail_after_save)
    with pytest.raises(OSError, match='Reply'):
        slot.execute(DocumentRequest(slot.token, SaveCommand(str(path))))
    assert path.is_file() and edit.dirty and slot.session is None
    slot.execute(DocumentRequest(document_token(edit), fill(edit, 'minecraft:gold_block'), pickle.loads(pickle.dumps(edit))))
    assert len(calls) == 1 and edit.dirty


def test_operation_request_freezes_input_values(edit):
    values = {'offset': [1, 0, 0]}
    command = OperationCommand('Move blocks', edit.select(), values)
    values['offset'][0] = 9
    assert command.values['offset'] == [1, 0, 0]


def test_open_discards_old_resident_snapshot_and_history_path_is_parent_owned(edit, tmp_path):
    from structura_core import save_structure

    worker = Worker()
    path = tmp_path / 'other.nbt'
    save_structure(edit.snapshot(), path, edit.size)
    try:
        worker.submit_document(fill(edit), edit)
        assert isinstance(wait(worker), TaskSuccess)
        assert edit.history.path is not None
        worker.submit('open', path=str(path))
        assert worker._resident is None
        opened = wait(worker)
        assert isinstance(opened, TaskSuccess), opened
        worker.submit_document(fill(opened.payload), opened.payload)
        assert isinstance(wait(worker), TaskSuccess)
        assert worker._resident[0] is opened.payload
    finally:
        worker.close()
        wait_stopped(worker)


def test_document_command_kinds_match_registry_and_protected_mutations():
    from typing import get_args
    from structura_edit.task_protocol import DOCUMENT_COMMANDS, TaskKind
    from structura_edit.tasks import TASKS

    assert set(get_args(TaskKind)) == set(TASKS)
    assert {kind for kind in DOCUMENT_COMMANDS if TASKS[kind].protected} == {'apply', 'history', 'save'}
