import traceback

from .tasks import task_definition


class TaskRunner:
    def __init__(self, worker, *, started, finished, failed, progress):
        self.worker = worker
        self.started = started
        self.finished = finished
        self.failed = failed
        self.progress = progress
        self.kind = None
        self._callback = None

    @property
    def busy(self):
        return self.worker.busy

    @property
    def protected(self):
        return self.kind is not None and task_definition(self.kind).protected

    def submit(self, kind, callback, **args):
        if self.busy:
            return False
        task = task_definition(kind)
        try:
            self.worker.submit(kind, **args)
        except Exception as error:
            self.worker.close()
            self.failed(kind, f"{type(error).__name__}: {error}\n{traceback.format_exc()}")
            self.finished()
            return True
        self.kind, self._callback = kind, callback
        self.started(kind, task)
        return True

    def poll(self):
        update = self.worker.progress()
        if update is not None:
            self.progress(*update)
        result = self.worker.poll() if self.busy else None
        if result is None:
            return
        kind, callback = self.kind, self._callback
        self.kind = self._callback = None
        success, payload = result
        try:
            if success:
                callback(payload)
            else:
                self.failed(kind, payload)
        except Exception as error:
            self.failed(kind, f"{type(error).__name__}: {error}\n{traceback.format_exc()}")
        finally:
            self.finished()

    def cancel(self):
        if self.protected:
            return False
        self.close()
        return True

    def close(self):
        self.worker.close()
        self.kind = self._callback = None
