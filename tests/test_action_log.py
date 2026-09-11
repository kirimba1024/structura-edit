import json

from structura_edit.action_log import ActionLog
from structura_edit.history_panel import HistoryPanel
from structura_edit.task_runner import TaskRunner
from test_task_runner import FakeWorker


def test_task_log_finishes_correct_record_when_callback_starts_another_task(tmp_path):
    log = ActionLog(tmp_path)
    tasks = TaskRunner(FakeWorker(), started=lambda *args: None, finished=lambda: None,
                       failed=lambda *args: None, progress=lambda *args: None, audit=log)
    try:
        tasks.submit('open', lambda result: tasks.submit('render', lambda result: None), path='input.nbt')
        tasks.worker.complete('session')
        tasks.poll()
        assert [row['status'] for row in log.records.values()] == ['Done', 'Running']
        tasks.worker.complete('Broken geometry', success=False)
        tasks.poll()
        assert [row['status'] for row in log.records.values()] == ['Done', 'Failed']
    finally:
        tasks.close()
        log.close()
    records = [json.loads(line) for line in (tmp_path/'actions.jsonl').read_text().splitlines()]
    assert records[-1]['error'] == 'Broken geometry'
    assert records[0]['details']['path'] == 'input.nbt'


def test_one_history_only_restores_edit_events_from_current_document(qt_app, edit, tmp_path):
    from PySide6.QtCore import Qt

    log = ActionLog(tmp_path)
    panel = HistoryPanel()
    panel.audit = log
    edit.apply(edit.set_block((0, 0, 0), 'minecraft:gold_block'))
    event = log.start('apply', {'session':edit})
    log.finish(event, result=edit)
    log.note('export', {'path': 'test.nbt'})
    restored = []
    panel.requested.connect(restored.append)
    try:
        panel.set_session(edit)
        panel.refresh()
        panel.list.setCurrentIndex(panel.model.index(0, 0))
        assert panel.restore.isEnabled() and not restored
        panel.restore.click()
        assert restored == [1]
        panel.list.setCurrentIndex(panel.model.index(1, 0))
        assert not panel.restore.isEnabled()
        assert panel.model.index(1, 0).data(Qt.ItemDataRole.UserRole) is None
        panel.set_session(None)
        panel.refresh()
        assert all(row[2] is None for row in panel.model.rows)
    finally:
        panel.close()
        log.close()


def test_action_log_bounds_memory_and_marks_cancelled_tasks(tmp_path):
    log = ActionLog(tmp_path, limit=3)
    try:
        for index in range(8):
            log.note('refresh', {'radius':index})
        identifier = log.start('world')
        log.finish(identifier, 'Cancelled')
        assert len(log.records) == 3
        assert log.records[identifier]['status'] == 'Cancelled'
    finally:
        log.close()
