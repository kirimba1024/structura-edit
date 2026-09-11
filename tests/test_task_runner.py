from collections import deque

import pytest

from structura_edit.task_runner import TaskRunner
from structura_edit.task_protocol import SubmitResult, TaskState, TaskProgress, TaskSuccess, TaskFailure


class FakeWorker:
    def __init__(self):
        self.busy = False
        self.stopping = False
        self.current_task_id = None
        self.results = deque()
        self.updates = deque()
        self.submissions = []
        self.error = None

    def submit(self, kind, *, task_id, **args):
        if self.error:
            raise self.error
        self.busy = True
        self.current_task_id = task_id
        self.submissions.append((kind, args))

    def complete(self, payload, *, success=True):
        self.results.append(TaskSuccess(self.current_task_id, payload) if success else TaskFailure(self.current_task_id, payload))

    def poll(self):
        if self.results:
            result = self.results.popleft()
            if result.task_id == self.current_task_id:
                self.busy = False
            return result
        return None

    def progress(self):
        return self.updates.popleft() if self.updates else None

    def close(self):
        self.busy = False
        self.results.clear()
        self.updates.clear()


@pytest.fixture
def runner():
    events = []
    runner = TaskRunner(FakeWorker(), started=lambda kind, task: events.append(("started", kind)),
                        finished=lambda: events.append(("finished",)),
                        failed=lambda kind, message: events.append(("failed", kind, message)),
                        progress=lambda *update: events.append(("progress", *update)))
    return runner, events


def test_callback_can_start_next_task_without_losing_its_state(runner):
    tasks, events = runner
    received = []
    tasks.submit("open", lambda session: tasks.submit("render", received.append, session=session), path="input.nbt")
    assert not tasks.submit("save", received.append)
    tasks.worker.updates.append(TaskProgress(tasks.current_task_id, "Open", 1, 2))
    tasks.worker.complete("session")
    tasks.poll()
    assert tasks.busy and tasks.kind == "render"
    assert tasks.worker.submissions[-1] == ("render", {"session": "session"})
    tasks.worker.complete("geometry")
    tasks.poll()
    assert received == ["geometry"] and not tasks.busy and tasks.kind is None
    assert ("progress", "Open", 1, 2) in events


def test_start_failure_reports_error_and_allows_retry(runner):
    tasks, events = runner
    tasks.worker.error = OSError("Cannot start process")
    assert tasks.submit("open", lambda result: None) is SubmitResult.FAILED_TO_START
    assert tasks.state is TaskState.FAILED
    assert not tasks.busy and tasks.kind is None
    assert events[0][:2] == ("failed", "open")
    assert events[0][2].startswith("OSError: Cannot start process")
    assert events[-1] == ("finished",)
    tasks.worker.error = None
    assert tasks.submit("open", lambda result: None)
    assert tasks.busy


@pytest.mark.parametrize("kind", ["apply", "save", "export", "history"])
def test_protected_tasks_cannot_be_cancelled(runner, kind):
    tasks, _ = runner
    received = []
    tasks.submit(kind, received.append)
    assert tasks.protected and not tasks.cancel() and tasks.busy
    tasks.worker.complete("completed")
    tasks.poll()
    assert received == ["completed"] and not tasks.protected


def test_cancellation_discards_old_result_and_accepts_new_task(runner):
    tasks, _ = runner
    received = []
    tasks.submit("recipe", received.append)
    tasks.worker.complete("cancelled result")
    assert tasks.cancel()
    tasks.submit("open", received.append)
    tasks.worker.complete("new result")
    tasks.poll()
    assert received == ["new result"]


def test_callback_failure_keeps_traceback_and_releases_task(runner):
    tasks, events = runner
    def receive(result):
        raise ValueError("Invalid geometry")
    tasks.submit("render", receive)
    tasks.worker.complete("geometry")
    tasks.poll()
    failure = next(event for event in events if event[0] == "failed")
    assert failure[1] == "render"
    assert failure[2].startswith("ValueError: Invalid geometry")
    assert "in receive" in failure[2]
    assert not tasks.busy and tasks.kind is None


def test_worker_failure_does_not_deliver_payload_to_callback(runner):
    tasks, events = runner
    received = []
    tasks.submit("world", received.append)
    tasks.worker.complete("World unavailable", success=False)
    tasks.poll()
    assert not received and not tasks.busy
    assert ("failed", "world", "World unavailable") in events


def test_unknown_task_is_rejected_before_starting_worker(runner):
    tasks, events = runner
    with pytest.raises(ValueError, match="Unknown task"):
        tasks.submit("unknown", lambda result: None)
    assert not tasks.worker.submissions and not events


def test_old_progress_success_and_failure_cannot_complete_new_task(runner):
    tasks, events = runner
    received = []
    tasks.submit('recipe', received.append)
    old = tasks.current_task_id
    tasks.cancel()
    tasks.submit('open', received.append)
    current = tasks.current_task_id
    assert old != current
    tasks.worker.updates.append(TaskProgress(old, 'Old', 1, 1))
    tasks.worker.results.extend((TaskSuccess(old, 'old'), TaskFailure(old, 'old failure')))
    tasks.poll()
    tasks.poll()
    assert tasks.current_task_id == current and tasks.busy and not received
    assert not any(event[0] in ('progress', 'failed', 'finished') for event in events)
    tasks.worker.complete('new')
    tasks.poll()
    assert received == ['new'] and tasks.state is TaskState.IDLE
    tasks.poll()
    assert events.count(('finished',)) == 1


def test_progress_callback_can_cancel_and_start_next_without_consuming_its_reply(runner):
    tasks, _ = runner
    received = []
    def progress(*args):
        tasks.cancel()
        tasks.submit('open', received.append)
        tasks.worker.complete('next')
    tasks.progress = progress
    tasks.submit('recipe', lambda _: pytest.fail('Cancelled callback'))
    tasks.worker.updates.append(TaskProgress(tasks.current_task_id, 'Running', 1, 2))
    tasks.poll()
    assert tasks.kind == 'open' and not received
    tasks.poll()
    assert received == ['next']


def test_callback_starting_next_then_failing_does_not_release_the_next_task(runner):
    tasks, events = runner
    received = []
    def completed(_):
        tasks.submit('render', received.append)
        raise ValueError('Callback failed after scheduling')
    tasks.submit('open', completed)
    tasks.worker.complete('document')
    tasks.poll()
    assert tasks.state is TaskState.RUNNING and tasks.kind == 'render'
    assert any(event[:2] == ('failed', 'open') for event in events)
    tasks.worker.complete('rendered')
    tasks.poll()
    assert received == ['rendered']


def test_cancelling_remains_busy_until_exchange_has_stopped(runner):
    tasks, _ = runner
    tasks.submit('render', lambda _: pytest.fail('Cancelled callback'))
    tasks.worker.stopping = True
    tasks.cancel()
    assert tasks.state is TaskState.CANCELLING and tasks.busy
    assert tasks.submit('open', lambda _: None) is SubmitResult.BUSY
    tasks.poll()
    assert tasks.busy
    tasks.worker.stopping = False
    tasks.poll()
    assert tasks.state is TaskState.IDLE
    assert tasks.submit('open', lambda _: None) is SubmitResult.STARTED


def test_started_observer_failure_does_not_cancel_a_dispatched_protected_write(runner):
    tasks, events = runner
    received = []
    def started(*args):
        raise RuntimeError('Cannot show progress')
    tasks.started = started
    assert tasks.submit('save', received.append) is SubmitResult.STARTED
    assert tasks.busy and tasks.protected and not tasks.cancel()
    tasks.worker.complete('saved')
    tasks.poll()
    assert received == ['saved'] and not tasks.busy
    assert events.count(('finished',)) == 1
