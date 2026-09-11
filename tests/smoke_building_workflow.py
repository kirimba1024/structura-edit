import argparse
import json
import os
import subprocess
import threading
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic, perf_counter

from PySide6.QtCore import QCoreApplication, QEvent, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox
from structura_core import save_structure

from building_fixture import building_source, content
from smoke_gui import check_recipe_invalidation, settle
from structura_edit import EditSession
from structura_edit.picking import Hit
from structura_edit.ui import EditorWindow


class Measurements:
    def __init__(self, window):
        self.window = window
        self.stages = {}
        self.peak_rss = self.samples = 0
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.sample, daemon=True)
        self.thread.start()

    def sample(self):
        while not self.stop.is_set():
            process = self.window.tasks.worker._process
            try:
                worker = process.pid if process is not None else None
                pids = ','.join(str(pid) for pid in (os.getpid(), worker) if pid)
                rows = subprocess.check_output(['ps', '-o', 'rss=', '-p', pids], text=True).split()
                self.peak_rss = max(self.peak_rss, sum(int(value) * 1024 for value in rows))
                self.samples += 1
            except (ValueError, OSError, subprocess.CalledProcessError):
                pass
            self.stop.wait(0.02)

    def run(self, name, action):
        gaps = []
        previous = perf_counter()
        def heartbeat():
            nonlocal previous
            now = perf_counter()
            gaps.append((now - previous) * 1000)
            previous = now
        timer = QTimer()
        timer.setInterval(16)
        timer.timeout.connect(heartbeat)
        timer.start()
        started = perf_counter()
        try:
            action()
            settle(self.window)
        finally:
            timer.stop()
        self.stages[name] = dict(elapsed_ms=round((perf_counter() - started) * 1000, 2),
                                 gui_timer_max_gap_ms=round(max([*gaps, (perf_counter() - previous) * 1000]), 2), timer_samples=len(gaps))
        print(name, json.dumps(self.stages[name]), flush=True)

    def finish(self):
        self.stop.set()
        self.thread.join(timeout=2)
        return dict(stages=self.stages, gui_and_worker_sampled_peak_rss_mib=round(self.peak_rss / 1024**2, 2),
                    rss_samples=self.samples, rss_sampling='ps RSS sum every 20 ms plus subprocess time; shared pages may be counted twice')


def accept_dialog():
    dialog = QApplication.activeModalWidget()
    if isinstance(dialog, QInputDialog):
        dialog.accept()
    elif isinstance(dialog, QMessageBox):
        button = dialog.button(QMessageBox.StandardButton.Discard) or dialog.button(QMessageBox.StandardButton.Ok)
        if button is not None:
            button.click()


def check_cancel(window):
    selected = window.document.selected.current
    window.planar.toggle()
    window.planar.pick(Hit((3, 2, 0), (0, 0, -1)))
    assert window.tasks.kind == 'planar'
    QTest.keyClick(window.plotter, Qt.Key.Key_Escape)
    settle(window)
    assert not window.planar.active and window.document.selected.current == selected
    window.selection_actions.set_bounds((0, 0, 0), (32, 5, 1))
    window.paint.active = True
    window.menus.actions['paint'].setChecked(True)
    window.paint.token = window.document.input_token
    window.paint.points = [(0.5, 0.5, 0.5), (31.5, 4.5, 0.5)]
    window.paint.finish()
    assert window.tasks.kind == 'paint'
    QTest.keyClick(window.plotter, Qt.Key.Key_Escape)
    settle(window)
    assert not window.paint.active and window.document.pending is None
    assert not window.document.session.dirty


def journey(window, root, output, measurements):
    source = building_source()
    original = root / 'building.nbt'
    save_structure(source, original, source.size)
    original_bytes = original.read_bytes()
    run = measurements.run
    run('open', lambda: window.sources.open_path(original))
    window.navigation.stop()
    run('cancel_tools', lambda: check_cancel(window))
    window.planar.toggle()
    run('wall_select', lambda: window.planar.pick(Hit((3, 2, 0), (0, 0, -1))))
    assert window.document.selection().volume == 157
    window.operation.fields['depth'].setValue(1)
    run('wall_preview', window.preview_operation)
    assert window.document.pending.report.added == 157
    run('wall_apply', window.apply_pending)
    assert window.document.session.origin == (0, 0, -1)
    window.selection_actions.set_bounds((0, 0, 0), window.document.session.size)
    window.repeat.start()
    window.repeat.bar.copies.setValue(3)
    window.repeat.bar.air.setChecked(True)
    run('floors_preview', window.repeat.preview)
    run('floors_apply', window.apply_pending)
    before_move = content(window.document.session.snapshot()), window.document.session.origin
    window.selection_actions.set_bounds((0, 0, 0), window.document.session.size)
    run('take_start', lambda: window.placement.start('take'))
    window.placement.set_position((-40, -3, -32))
    run('take_review', window.placement.bar.preview.click)
    assert window.document.pending is not None
    window.grab().save(str(output / 'take-review.png'))
    window.plotter.screenshot(str(output / 'take-scene.png'))
    run('take_apply', window.placement.bar.apply.click)
    moved = content(window.document.session.snapshot()), window.document.session.origin
    assert len(moved[0][2]) == len(moved[0][3]) == 4
    working = root / 'working.nbt'
    run('save', lambda: window.sources.save_path(working))
    assert not window.document.session.dirty and content(EditSession.open(working).snapshot()) == moved[0]
    run('undo_take', window.undo)
    assert (content(window.document.session.snapshot()), window.document.session.origin) == before_move
    assert window.document.session.dirty
    run('draft_save', window.drafts.save)
    saved_bytes = working.read_bytes()
    dialogs = QTimer()
    dialogs.setInterval(25)
    dialogs.timeout.connect(accept_dialog)
    dialogs.start()
    try:
        run('draft_recover', window.drafts.recover)
    finally:
        dialogs.stop()
    assert (content(window.document.session.snapshot()), window.document.session.origin) == before_move
    assert not window.document.session.can_undo and window.document.session.dirty
    assert working.read_bytes() == saved_bytes and original.read_bytes() == original_bytes
    run('recovered_save', window.sources.save_dialog)
    assert not window.document.session.dirty and content(EditSession.open(working).snapshot()) == before_move[0]
    assert not window.scene.ghost_actors and not window.placement.view.actors and not window.placement.active
    assert not window.placement.bar.placement.isVisible()
    window.grab().save(str(output / 'recovered.png'))
    window.plotter.screenshot(str(output / 'recovered-scene.png'))
    window.selection_actions.set_bounds((0, 0, 0), (1, 1, 1))
    run('recipe_invalidation', lambda: check_recipe_invalidation(window))
    assert original.read_bytes() == original_bytes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path('/private/tmp/structura-building-workflow'))
    parser.add_argument('--visible', action='store_true')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs)
    app = QApplication([])
    with TemporaryDirectory(prefix='structura-building-') as temporary:
        root = Path(temporary)
        os.environ['STRUCTURA_EDIT_DATA'] = str(root / 'local')
        window = EditorWindow(off_screen=not args.visible, cache_dir=root / 'cache')
        window.resize(1104, 720)
        window.show()
        window.drafts.last_attempt = monotonic() + 3600
        measurements = Measurements(window)
        try:
            journey(window, root, args.output, measurements)
            result = dict(measurements.finish(), viewport=[window.plotter.width(), window.plotter.height()],
                          visible=args.visible, assertions='Wall with chest and glass, four floors, Take, Save, Undo, draft recovery, repeated Save, stale recipe rejection')
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
