import traceback
from uuid import uuid4

from .task_protocol import SubmitResult, TaskState, TaskSuccess
from .tasks import task_definition


class TaskRunner:
    def __init__(self, worker, *, started, finished, failed, progress, audit=None):
        self.worker = worker
        self.started = started
        self.finished = finished
        self.failed = failed
        self.progress = progress
        self.kind = None
        self.current_task_id = None
        self.state = TaskState.IDLE
        self._callback = None
        self.audit = audit
        self._event = None

    @property
    def busy(self):
        return self.state in (TaskState.STARTING, TaskState.RUNNING, TaskState.CANCELLING)

    @property
    def protected(self):
        return self.kind is not None and task_definition(self.kind).protected

    @property
    def selection_busy(self):
        return self.busy and (self.kind is None or task_definition(self.kind).blocks_selection)

    def submit(self, kind, callback, **args):
        return self._submit(kind, callback, args, lambda task_id: self.worker.submit(kind, task_id=task_id, **args))

    def submit_document(self, command, callback, *, session):
        return self._submit(command.kind, callback, dict(vars(command), session=session),
                            lambda task_id: self.worker.submit_document(command, session, task_id=task_id))

    def _submit(self, kind, callback, args, dispatch):
        if self.busy:
            return SubmitResult.BUSY
        task = task_definition(kind)
        event = self.audit.start(kind, args) if self.audit else None
        task_id = uuid4().hex
        self.kind, self._callback = kind, callback
        self.current_task_id, self._event = task_id, event
        self.state = TaskState.STARTING
        try:
            dispatch(task_id)
        except Exception as error:
            self.worker.close()
            self._release(TaskState.CANCELLING if self.worker.stopping else TaskState.FAILED)
            if self.audit:
                self.audit.finish(event, 'Failed', error=error)
            self.failed(kind, f'{type(error).__name__}: {error}\n{traceback.format_exc()}')
            self.finished()
            return SubmitResult.FAILED_TO_START
        self.state = TaskState.RUNNING
        try:
            self.started(kind, task)
        except Exception as error:
            self.failed(kind, f'{type(error).__name__}: {error}\n{traceback.format_exc()}')
        return SubmitResult.STARTED

    def _release(self, state):
        self.kind = self._callback = self.current_task_id = self._event = None
        self.state = state

    def poll(self):
        if self.state is TaskState.CANCELLING:
            if not self.worker.stopping:
                self.state = TaskState.IDLE
                self.finished()
            return
        if self.state is not TaskState.RUNNING:
            return
        task_id = self.current_task_id
        update = self.worker.progress()
        if update is not None and update.task_id == task_id:
            self.progress(update.label, update.done, update.total)
        if self.current_task_id != task_id or self.state is not TaskState.RUNNING:
            return
        result = self.worker.poll()
        if result is None or result.task_id != task_id:
            return
        kind, callback, event = self.kind, self._callback, self._event
        success = isinstance(result, TaskSuccess)
        self._release(TaskState.IDLE if success else TaskState.FAILED)
        try:
            if success:
                callback(result.payload)
            else:
                if self.audit:
                    self.audit.finish(event, 'Failed', error=result.message)
                self.failed(kind, result.message)
            if success and self.audit:
                self.audit.finish(event, result=result.payload)
        except Exception as error:
            if self.current_task_id is None:
                self.state = TaskState.FAILED
            if self.audit:
                self.audit.finish(event, 'Failed', error=error)
            self.failed(kind, f'{type(error).__name__}: {error}\n{traceback.format_exc()}')
        finally:
            self.finished()

    def cancel(self):
        if self.protected:
            return False
        self.close()
        return True

    def close(self):
        if self.audit and self._event is not None:
            self.audit.finish(self._event, 'Cancelled')
        self.worker.close()
        self._release(TaskState.CANCELLING if self.worker.stopping else TaskState.IDLE)
