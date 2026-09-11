from random import Random
from time import monotonic, sleep

import pytest

from structura_edit import EditSession
from structura_edit.editor_document import EditorDocument
from structura_edit.edit_workflow import EditWorkflow
from structura_edit.jobs import Worker
from structura_edit.task_runner import TaskRunner
from structura_edit.task_protocol import TaskState


def settle(tasks):
    deadline = monotonic() + 10
    while tasks.busy and monotonic() < deadline:
        tasks.poll()
        sleep(0.001)
    assert not tasks.busy


@pytest.mark.parametrize('seed', [5, 19, 41])
def test_background_edit_sequences_match_committed_history_model(structure, tmp_path, seed):
    random = Random(seed)
    document = EditorDocument()
    errors = []
    tasks = TaskRunner(Worker(), started=lambda *_: None, finished=lambda: None,
                       failed=lambda kind, message: errors.append((kind, message)), progress=lambda *_: None)
    edits = EditWorkflow(document, tasks, previewed=lambda _: None, updated=lambda _: None)
    values, cursor, saved = ['minecraft:stone'], 0, 'minecraft:stone'
    def opened():
        session = EditSession.from_structure(structure)
        document.load(session)
        document.selected.set_bounds((0, 0, 0), (1, 1, 1))
    opened()
    try:
        for _ in range(45):
            action = random.choice(('apply', 'apply', 'undo', 'redo', 'save', 'late', 'cancel', 'failure', 'reopen'))
            if action == 'apply':
                target = random.choice(('minecraft:glass', 'minecraft:gold_block', 'minecraft:stone'))
                assert edits.prepare('operation', mode='Fill', values={'target': target})
                settle(tasks)
                assert document.preview is not None
                assert edits.commit(document.pending, lambda _: None)
                settle(tasks)
                if target != values[cursor]:
                    values[cursor + 1:] = [target]
                    cursor += 1
            elif action in ('undo', 'redo'):
                index = cursor + (-1 if action == 'undo' else 1)
                if 0 <= index < len(values):
                    assert edits.seek_history(index, lambda _: None)
                    settle(tasks)
                    cursor = index
            elif action == 'save':
                assert edits.save(tmp_path / f'{seed}.nbt', lambda _: None)
                settle(tasks)
                saved = values[cursor]
            elif action in ('late', 'cancel', 'failure'):
                count = len(errors)
                code = ('raise ValueError("Injected recipe failure")' if action == 'failure'
                        else 'edit.apply(edit.fill(selection, "minecraft:diamond_block"))')
                assert edits.prepare('recipe', code=code)
                if action == 'late':
                    edits.invalidate()
                elif action == 'cancel':
                    assert tasks.cancel()
                settle(tasks)
                assert document.preview is None
                assert len(errors) == count + (action == 'failure')
            else:
                assert edits.prepare('operation', mode='Fill', values={'target': 'minecraft:diamond_block'})
                opened()
                values, cursor, saved = ['minecraft:stone'], 0, 'minecraft:stone'
                settle(tasks)
                assert document.preview is None
            session = document.session
            assert session.state_at((0, 0, 0)) == values[cursor]
            assert session.history.cursor == cursor
            assert len(session.history.entries) == len(values) - 1
            assert session.dirty == (values[cursor] != saved)
            assert tasks.current_task_id is None and tasks.state in (TaskState.IDLE, TaskState.FAILED)
    finally:
        tasks.close()
        settle(tasks)
