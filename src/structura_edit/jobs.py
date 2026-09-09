import multiprocessing
import queue
import threading
import traceback
from time import monotonic


def _serve(connection):
    from .runtime_code import CodeVersion
    from .tasks import execute
    from .object_search import ObjectSearch

    code = CodeVersion()
    object_search = ObjectSearch()
    last_progress = 0
    def progress(label, done, total):
        nonlocal last_progress
        now = monotonic()
        if done == total or now - last_progress >= 0.05:
            connection.send(("progress", label, done, total))
            last_progress = now
    try:
        while True:
            kind, args = connection.recv()
            try:
                code.check()
                connection.send((True, execute(kind, args, progress, object_search=object_search)))
            except BaseException as error:
                connection.send((False, f"{type(error).__name__}: {error}\n{traceback.format_exc(limit=8)}"))
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
        self._closing = threading.Event()
        self.busy = False

    def _start(self):
        context = multiprocessing.get_context("spawn")
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

    def submit(self, kind, *, prepare_args=None, **args):
        if self.busy:
            raise RuntimeError("A task is already running")
        if self._process is None or not self._process.is_alive():
            if self._process is not None:
                self.close()
            self._start()
        self.busy = True
        self._progress = queue.Queue(maxsize=1)
        updates = self._progress
        connection, results, closing = self._connection, self._results, self._closing

        def exchange():
            try:
                payload = prepare_args() if prepare_args is not None else args
                if closing.is_set():
                    return
                connection.send((kind, payload))
                while True:
                    result = connection.recv()
                    if result[0] != "progress":
                        break
                    try:
                        updates.get_nowait()
                    except queue.Empty:
                        pass
                    updates.put_nowait(result[1:])
            except Exception as error:
                result = False, f"{type(error).__name__}: {error}"
            finally:
                if closing.is_set():
                    connection.close()
            results.put(result)

        self._exchange = threading.Thread(target=exchange, daemon=True)
        self._exchange.start()

    def poll(self):
        try:
            result = self._results.get_nowait()
        except queue.Empty:
            return None
        self.busy = False
        return result

    def progress(self):
        try:
            return self._progress.get_nowait()
        except queue.Empty:
            return None

    def close(self):
        self._closing.set()
        if self._process is not None:
            self._process.terminate()
            self._process.join(timeout=0.5)
            if self._process.is_alive():
                self._process.kill()
                self._process.join(timeout=0.5)
            self._process.close()
        if self._connection is not None and (self._exchange is None or not self._exchange.is_alive()):
            self._connection.close()
        self._process = self._connection = None
        self._results = queue.Queue()
        self._progress = queue.Queue(maxsize=1)
        self._exchange = None
        self._closing = threading.Event()
        self.busy = False
