import gc
import json
import threading
from contextlib import ExitStack
from functools import wraps
from time import perf_counter, thread_time
from unittest.mock import patch

from PySide6.QtCore import QTimer


class WorkflowTrace:
    def __init__(self, output):
        self.output = output
        self.events = []
        self.collections = {}

    def record(self, name, start, cpu, **values):
        self.events.append(dict(name=name, start_ms=(start - self.started) * 1000,
                                elapsed_ms=(perf_counter() - start) * 1000,
                                cpu_ms=(thread_time() - cpu) * 1000,
                                thread=threading.current_thread().name, **values))

    def wrap(self, name, function):
        @wraps(function)
        def measured(*args, **kwargs):
            start, cpu = perf_counter(), thread_time()
            try:
                return function(*args, **kwargs)
            finally:
                self.record(name, start, cpu)
        return measured

    def collect(self, phase, info):
        key = threading.get_ident(), info['generation']
        if phase == 'start':
            self.collections[key] = perf_counter(), thread_time()
        else:
            start, cpu = self.collections.pop(key, (perf_counter(), thread_time()))
            self.record('gc', start, cpu, **info)

    def heartbeat(self):
        now = perf_counter()
        if now - self.previous > 0.032:
            self.events.append(dict(name='gui_gap', start_ms=(self.previous - self.started) * 1000,
                                    elapsed_ms=(now - self.previous) * 1000))
        self.previous = now

    def __enter__(self):
        from multiprocessing.connection import _ForkingPickler

        from structura_edit.editor_document import EditorDocument
        from structura_edit.render_source import RenderSource
        from structura_edit.session import EditSession
        from structura_edit.view_pipeline import ViewRequest, ViewPipeline

        self.started = self.previous = perf_counter()
        self.stack = ExitStack()
        for owner, method in [(_ForkingPickler, 'loads'), (_ForkingPickler, 'dumps'),
                              (EditSession, '_check_change'), (EditSession, '_apply_cells'),
                              (EditorDocument, 'show_preview'), (ViewRequest, 'geometry_args'),
                              (RenderSource, 'prepare_grid'), (ViewPipeline, '_install_next')]:
            name = f'{owner.__name__}.{method}'
            self.stack.enter_context(patch.object(owner, method, self.wrap(name, getattr(owner, method))))
        gc.callbacks.append(self.collect)
        self.timer = QTimer()
        self.timer.setInterval(16)
        self.timer.timeout.connect(self.heartbeat)
        self.timer.start()
        return self

    def __exit__(self, *exc):
        self.timer.stop()
        gc.callbacks.remove(self.collect)
        self.stack.close()
        self.output.write_text(json.dumps(sorted(self.events, key=lambda event: event['start_ms']), indent=2))
