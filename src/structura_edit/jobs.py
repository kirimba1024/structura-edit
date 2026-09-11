import multiprocessing
import queue
import threading
import traceback
from dataclasses import replace
from time import monotonic
from uuid import uuid4

from .task_protocol import DocumentRequest, TaskCall, TaskRequest, TaskProgress, TaskSuccess, TaskFailure
from .worker_document import WorkerDocument, document_token, matches_document


def _serve(connection):
    from .runtime_code import CodeVersion
    from .tasks import execute, task_definition
    from .object_search import ObjectSearch

    code = CodeVersion()
    object_search = ObjectSearch()
    document = WorkerDocument()
    try:
        while True:
            request = connection.recv()
            if not isinstance(request, TaskRequest):
                raise ValueError('Invalid worker request')
            last_progress = 0
            def progress(label, done, total):
                nonlocal last_progress
                now = monotonic()
                if done == total or now - last_progress >= 0.05:
                    connection.send(TaskProgress(request.task_id, label, done, total))
                    last_progress = now
            try:
                code.check()
                command = request.command
                if task_definition(command.kind).replaces_document:
                    document.clear()
                    object_search = ObjectSearch()
                token = None
                if isinstance(command, DocumentRequest):
                    payload, token = document.execute(command, progress, object_search=object_search)
                else:
                    payload = execute(command.kind, command.args, progress, object_search=object_search)
                connection.send(TaskSuccess(request.task_id, payload, token))
            except BaseException as error:
                document.clear()
                connection.send(TaskFailure(request.task_id, f'{type(error).__name__}: {error}\n{traceback.format_exc(limit=8)}'))
    except (EOFError, BrokenPipeError, OSError):
        pass
    finally:
        connection.close()


class Worker:
    def __init__(self):
        self._process = None
        self._connection = None
        self._results = queue.Queue()
        self._progress = queue.Queue(maxsize=1)
        self._exchange = None
        self._retiring = None
        self._closing = threading.Event()
        self.current_task_id = None
        self._resident = None
        self._pending_document = None

    @property
    def stopping(self):
        return self._retiring is not None and self._retiring.is_alive()

    @property
    def busy(self):
        return self.current_task_id is not None or self.stopping

    def _start(self):
        context = multiprocessing.get_context('spawn')
        connection, child = context.Pipe()
        process = context.Process(target=_serve, args=(child,), daemon=True)
        try:
            process.start()
        except Exception:
            connection.close()
            process.close()
            raise
        finally:
            child.close()
        self._connection, self._process = connection, process

    def submit_document(self, command, session, *, task_id=None):
        return self.submit(command.kind, task_id=task_id, document=(command, session))

    def submit(self, kind, *, task_id=None, prepare_args=None, document=None, **args):
        from .tasks import task_definition

        if self.busy:
            raise RuntimeError('A task is already running or stopping')
        task = task_definition(kind)
        if self._process is None or not self._process.is_alive():
            if self._process is not None:
                self.close()
            self._start()
        if task.replaces_document:
            self._resident = None
        command = None
        if document is not None:
            command, session = document
            session.history.prepare()
            resident = self._resident
            if (resident is not None and resident[0] is session and resident[1] is session._document
                    and matches_document(resident[2], session)):
                token, snapshot = resident[2], None
            else:
                token, snapshot = document_token(session), session
            source = session._document
            self._pending_document = session, source, token, command.kind
            command = DocumentRequest(token, command, snapshot)
        task_id = task_id or uuid4().hex
        self.current_task_id = task_id
        self._progress = queue.Queue(maxsize=1)
        updates = self._progress
        connection, results, closing = self._connection, self._results, self._closing

        def exchange():
            try:
                prepared = command if command is not None else TaskCall(kind, prepare_args() if prepare_args else args)
                if closing.is_set():
                    return
                connection.send(TaskRequest(task_id, prepared))
                while True:
                    result = connection.recv()
                    if not isinstance(result, (TaskProgress, TaskSuccess, TaskFailure)):
                        raise ValueError('Invalid worker response')
                    if result.task_id != task_id:
                        continue
                    if not isinstance(result, TaskProgress):
                        break
                    try:
                        updates.get_nowait()
                    except queue.Empty:
                        pass
                    updates.put_nowait(result)
                if isinstance(result, TaskSuccess) and isinstance(prepared, DocumentRequest):
                    from .worker_delta import DocumentDelta

                    if isinstance(result.payload, DocumentDelta):
                        if session._document is not source:
                            raise ValueError('The document source changed while the task was running')
                        result = replace(result, payload=result.payload.restore(session, prepared.token, result.document))
            except Exception as error:
                result = TaskFailure(task_id, f'{type(error).__name__}: {error}\nThe task was not retried.')
            finally:
                if closing.is_set():
                    connection.close()
            if not closing.is_set():
                results.put(result)

        self._exchange = threading.Thread(target=exchange, name='worker-exchange', daemon=True)
        try:
            self._exchange.start()
        except Exception:
            self._exchange = None
            self.close()
            raise
        return task_id

    def poll(self):
        if self._exchange is not None and self._exchange.is_alive():
            return None
        while True:
            try:
                result = self._results.get_nowait()
            except queue.Empty:
                return None
            if result.task_id == self.current_task_id:
                break
        if isinstance(result, TaskSuccess) and self._pending_document is not None:
            from .session import EditSession

            session, source, token, kind = self._pending_document
            if kind in ('apply', 'history', 'save'):
                returned = result.payload
                if (isinstance(returned, EditSession) and result.document is not None
                        and result.document.document_id == token.document_id
                        and result.document.revision >= token.revision and matches_document(result.document, returned)):
                    self._resident = returned, returned._document, result.document
                else:
                    result = TaskFailure(result.task_id, 'The worker returned an invalid document version')
            elif result.document == token:
                self._resident = session, source, token
            else:
                result = TaskFailure(result.task_id, 'The worker returned a result for a different document version')
        if isinstance(result, TaskFailure):
            self._resident = None
        self._pending_document = None
        self.current_task_id = None
        return result

    def progress(self):
        try:
            update = self._progress.get_nowait()
        except queue.Empty:
            return None
        return update if update.task_id == self.current_task_id else None

    def close(self):
        self._closing.set()
        self.current_task_id = None
        self._resident = self._pending_document = None
        if self._process is not None:
            self._process.terminate()
            self._process.join(timeout=0.5)
            if self._process.is_alive():
                self._process.kill()
                self._process.join(timeout=0.5)
            self._process.close()
        if self._exchange is not None and self._exchange.is_alive():
            self._retiring = self._exchange
        elif self._connection is not None:
            self._connection.close()
        self._process = self._connection = None
        self._results = queue.Queue()
        self._progress = queue.Queue(maxsize=1)
        self._exchange = None
        self._closing = threading.Event()
