import argparse
import cProfile
import json
import os
import pstats
import threading
from contextlib import contextmanager, nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication
from structura_core import save_structure

from building_fixture import building_source, content
from smoke_building_workflow import Measurements
from workflow_trace import WorkflowTrace
from structura_edit import EditSession
from structura_edit.ui import EditorWindow


@contextmanager
def profile_exchanges(output):
    thread = threading.Thread
    count = 0
    def create_thread(*args, **kwargs):
        nonlocal count
        target = kwargs.get('target')
        if getattr(target, '__qualname__', '') == 'Worker.submit.<locals>.exchange':
            count += 1
            path = output / f'exchange-{count}'
            def profiled():
                profile = cProfile.Profile()
                try:
                    profile.runcall(target)
                finally:
                    profile.dump_stats(str(path.with_suffix('.prof')))
                    with path.with_suffix('.txt').open('w') as stream:
                        pstats.Stats(profile, stream=stream).strip_dirs().sort_stats('cumulative').print_stats(50)
            kwargs['target'] = profiled
        return thread(*args, **kwargs)
    with patch('structura_edit.jobs.threading.Thread', create_thread):
        yield


class ProfiledMeasurements(Measurements):
    def __init__(self, window, output, profile, trace=False):
        super().__init__(window)
        self.output = output
        self.profile = profile
        self.trace = trace

    def run(self, name, action):
        context = WorkflowTrace(self.output / f'{name}-trace.json') if self.trace else nullcontext()
        with context:
            self.measure(name, action)

    def measure(self, name, action):
        if not self.profile:
            return super().run(name, action)
        profile = cProfile.Profile()
        profile.enable()
        try:
            with profile_exchanges(self.output / name):
                (self.output / name).mkdir(exist_ok=True)
                super().run(name, action)
        finally:
            profile.disable()
            profile.dump_stats(str(self.output / f'{name}.prof'))
            with (self.output / f'{name}.txt').open('w') as stream:
                pstats.Stats(profile, stream=stream).strip_dirs().sort_stats('cumulative').print_stats(50)


def journey(window, root, output, measurements, floors):
    building = EditSession.from_structure(building_source())
    if floors > 1:
        building.apply(building.stack(building.select(), floors - 1, (0, 6, 0)))
    source = building.snapshot()
    original = root / 'building.nbt'
    save_structure(source, original, source.size)
    original_bytes = original.read_bytes()
    expected = content(source)
    run = measurements.run
    run('open', lambda: window.sources.open_path(original))
    window.navigation.stop()
    window.selection_actions.set_bounds((0, 0, 0), window.document.session.size)
    run('take_start', lambda: window.placement.start('take'))
    window.placement.set_position((-40, -3, -32))
    run('take_review', window.placement.bar.preview.click)
    assert window.document.pending is not None, window.status.text()
    changed_cells = len(window.document.pending)
    run('take_apply', window.placement.bar.apply.click)
    moved = content(window.document.session.snapshot()), window.document.session.origin
    assert len(moved[0][2]) == len(moved[0][3]) == floors
    working = root / 'working.nbt'
    run('save', lambda: window.sources.save_path(working))
    assert not window.document.session.dirty
    assert content(EditSession.open(working).snapshot()) == moved[0]
    run('undo_take', window.undo)
    assert content(window.document.session.snapshot()) == expected
    assert window.document.session.origin == (0, 0, 0) and window.document.session.dirty
    run('redo_take', window.redo)
    assert (content(window.document.session.snapshot()), window.document.session.origin) == moved
    assert not window.document.session.dirty
    assert original.read_bytes() == original_bytes
    window.grab().save(str(output / 'editor.png'))
    window.plotter.screenshot(str(output / 'scene.png'))
    return dict(floors=floors, source_size=source.size, source_blocks=len(expected[1]), changed_cells=changed_cells)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path('/private/tmp/structura-edit-workflow'))
    parser.add_argument('--floors', type=int, default=24)
    parser.add_argument('--profile', action='store_true')
    parser.add_argument('--trace', action='store_true')
    parser.add_argument('--visible', action='store_true')
    parser.add_argument('--full-session', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.floors <= 48:
        parser.error('--floors must be between 1 and 48')
    args.output.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    with TemporaryDirectory(prefix='structura-edit-workflow-') as temporary:
        root = Path(temporary)
        os.environ['STRUCTURA_EDIT_DATA'] = str(root / 'local')
        window = EditorWindow(off_screen=not args.visible, cache_dir=root / 'cache')
        if args.full_session:
            def submit_document(command, callback, *, session):
                source = session if command.kind in ('apply', 'save', 'history') else session.fork()
                return window.tasks.submit(command.kind, callback, session=source, **vars(command))
            window.tasks.submit_document = submit_document
        window.resize(1104, 720)
        window.show()
        window.drafts.last_attempt = monotonic() + 3600
        measurements = ProfiledMeasurements(window, args.output, args.profile, args.trace)
        try:
            fixture = journey(window, root, args.output, measurements, args.floors)
            result = dict(measurements.finish(), **fixture, visible=args.visible, profiled=args.profile, traced=args.trace,
                          resident_document=not args.full_session,
                          viewport=[window.plotter.width(), window.plotter.height()],
                          assertions='Take, Save and reload, Undo, Redo, block NBT, entities, bounds and untouched source')
            (args.output / 'result.json').write_text(json.dumps(result, indent=2))
            print(json.dumps(result), flush=True)
        finally:
            measurements.finish()
            window.document.load(None)
            window.close()
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            app.processEvents()


if __name__ == '__main__':
    main()
