from collections import deque

import pytest

from structura_edit.task_runner import TaskRunner


class FakeWorker:
    def __init__(self):
        self.busy = False
        self.results = deque()
        self.updates = deque()
        self.submissions = []
        self.error = None

    def submit(self, kind, **args):
        if self.error:
            raise self.error
        self.busy = True
        self.submissions.append((kind, args))

    def poll(self):
        if self.results:
            self.busy = False
            return self.results.popleft()
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
    tasks.worker.updates.append(("Open", 1, 2))
    tasks.worker.results.append((True, "session"))
    tasks.poll()
    assert tasks.busy and tasks.kind == "render"
    assert tasks.worker.submissions[-1] == ("render", {"session": "session"})
    tasks.worker.results.append((True, "geometry"))
    tasks.poll()
    assert received == ["geometry"] and not tasks.busy and tasks.kind is None
    assert ("progress", "Open", 1, 2) in events


def test_start_failure_reports_error_and_allows_retry(runner):
    tasks, events = runner
    tasks.worker.error = OSError("Cannot start process")
    assert tasks.submit("open", lambda result: None)
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
    tasks.worker.results.append((True, "completed"))
    tasks.poll()
    assert received == ["completed"] and not tasks.protected


def test_cancellation_discards_old_result_and_accepts_new_task(runner):
    tasks, _ = runner
    received = []
    tasks.submit("recipe", received.append)
    tasks.worker.results.append((True, "cancelled result"))
    assert tasks.cancel()
    tasks.submit("open", received.append)
    tasks.worker.results.append((True, "new result"))
    tasks.poll()
    assert received == ["new result"]


def test_callback_failure_keeps_traceback_and_releases_task(runner):
    tasks, events = runner
    def receive(result):
        raise ValueError("Invalid geometry")
    tasks.submit("render", receive)
    tasks.worker.results.append((True, "geometry"))
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
    tasks.worker.results.append((False, "World unavailable"))
    tasks.poll()
    assert not received and not tasks.busy
    assert ("failed", "world", "World unavailable") in events


def test_unknown_task_is_rejected_before_starting_worker(runner):
    tasks, events = runner
    with pytest.raises(ValueError, match="Unknown task"):
        tasks.submit("unknown", lambda result: None)
    assert not tasks.worker.submissions and not events
