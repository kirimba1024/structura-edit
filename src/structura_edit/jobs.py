import io
import multiprocessing
import queue
import threading
import traceback
from contextlib import redirect_stdout, redirect_stderr
from time import monotonic

from .source_loading import open_source

PROTECTED_JOBS = {"save", "export", "apply", "history"}


class _Output(io.StringIO):
    def write(self, text):
        if self.tell() > 16_000:
            self.seek(0)
            self.truncate()
        return super().write(text[-16_000:])


def execute(kind, args, progress=None):
    if kind in ("world", "render", "map", "clipboard", "placement"):
        from .resources import refresh_resources

        refresh_resources(args.get("assets"))
    if kind in ("clipboard", "placement"):
        from .placement_jobs import prepare_clipboard, prepare_placement

        prepare = prepare_clipboard if kind == "clipboard" else prepare_placement
        return prepare(**args, progress=progress)
    if kind == "world":
        from .preview import build_sections
        from .sections import prepare_sections

        session = open_source(**{key: args[key] for key in
                                ("path", "center", "dimension", "radius", "vertical_radius", "include_entities")},
                              world_changes=args.get("world_changes"))
        return session, build_sections(**prepare_sections(session), assets=args["assets"], progress=progress)
    if kind == "open":
        return open_source(**args)
    if kind == "save":
        args["session"].save(args["path"])
        return args["session"]
    if kind == "apply":
        args["session"].apply(args["change"])
        return args["session"]
    if kind == "history":
        session, index = args["session"], args["index"]
        if not 0 <= index <= len(session.history.entries):
            raise ValueError("Invalid history position")
        total = abs(index - session.history.cursor)
        while session.history.cursor != index:
            getattr(session, "undo" if index < session.history.cursor else "redo")()
            if progress:
                progress("History", total - abs(index - session.history.cursor), total)
        return session
    if kind == "render":
        from .preview import build_sections

        return build_sections(**args, progress=progress)
    if kind == "export":
        return args["session"].export_selection(args["selection"], args["path"])
    if kind == "map":
        import sqlite3
        from .map_cache import store_maps
        from .map_images import build_source_maps

        images = build_source_maps(args["source"], args["assets"], progress=progress)
        atlas = args.get("atlas")
        if atlas is not None:
            try:
                images, atlas = store_maps(atlas, images)
            except (OSError, ValueError, sqlite3.Error) as error:
                return images, None, f"Map cache unavailable: {error}"
        return images, atlas, ""
    if kind == "operation":
        from .commands import COMMANDS

        return COMMANDS[args["mode"]].execute(args["session"], args["selection"], **args["values"])
    if kind == "recipe":
        session = args["session"]
        branch = session.fork()
        output = _Output()
        namespace = {"edit": branch, "selection": args["selection"]}
        with redirect_stdout(output), redirect_stderr(output):
            exec(compile(args["code"], "<structura recipe>", "exec"), namespace)
        return session.diff(branch), output.getvalue()[-16_000:]
    raise ValueError(f"Unknown task: {kind}")


def _serve(connection):
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
                connection.send((True, execute(kind, args, progress)))
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

    def submit(self, kind, *, prepare_args=None, **args):
        if self.busy:
            raise RuntimeError("A task is already running")
        if self._process is None or not self._process.is_alive():
            if self._process is not None:
                self.close()
            context = multiprocessing.get_context("spawn")
            self._connection, child = context.Pipe()
            self._process = context.Process(target=_serve, args=(child,), daemon=True)
            self._process.start()
            child.close()
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
