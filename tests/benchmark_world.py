import argparse
import faulthandler
import json
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from time import perf_counter

import numpy as np
from PySide6.QtCore import QEventLoop, QTimer, Qt
from PySide6.QtWidgets import QApplication

from flight_metrics import FlightMetrics
from smoke_gui import settle
from structura_edit.ui import EditorWindow


def memory(window):
    worker = window.tasks.worker._process
    pids = [os.getpid()] + ([worker.pid] if worker is not None else [])
    result = subprocess.run(['ps', '-o', 'rss=', '-p', ','.join(map(str, pids))], capture_output=True, text=True)
    return sum(int(value) for value in result.stdout.split()) * 1024 if result.returncode == 0 else None


def measure(window, action):
    beats = [perf_counter()]
    heartbeat = QTimer()
    heartbeat.setTimerType(Qt.TimerType.PreciseTimer)
    heartbeat.timeout.connect(lambda: beats.append(perf_counter()))
    heartbeat.start(16)
    started = perf_counter()
    try:
        action()
        settle(window, timeout=120)
    finally:
        heartbeat.stop()
    elapsed = perf_counter() - started
    gaps = np.diff([*beats, perf_counter()]) * 1000
    assert not window.issues, window.issues
    return dict(seconds=elapsed, heartbeat_ms_p95=float(np.percentile(gaps, 95)),
                heartbeat_ms_max=float(max(gaps)), rss_gui_worker_bytes=memory(window))


def flight(window, seconds):
    window.navigation.stop()
    center = np.asarray(window.document.session.size) / 2
    extent = max(window.document.session.size)
    window.plotter.camera_position = [center + np.array((.2, .15, .35)) * extent, center, (0, 1, 0)]
    window.camera.needs_render = True
    window.camera.render()
    settle(window)
    metrics = FlightMetrics(window.plotter)
    loop = QEventLoop()
    motion = QTimer()
    motion.setTimerType(Qt.TimerType.PreciseTimer)
    def step():
        window.camera.translate((.025, 0, -.04))
        window.camera.look(.5, 0)
        window.camera.render()
    motion.timeout.connect(step)
    motion.start(16)
    QTimer.singleShot(round(seconds * 1000), loop.quit)
    loop.exec()
    motion.stop()
    return dict(metrics.finish(), viewport=list(window.plotter.render_window.GetSize()),
                actors=len(window.scene.actors), geometry_bytes=sum(window.scene.section_bytes.values()))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('world', type=Path)
    parser.add_argument('--radius', type=int, default=6)
    parser.add_argument('--visible', action='store_true')
    parser.add_argument('--flight-seconds', type=float, default=3)
    parser.add_argument('--output', type=Path, default=Path('/private/tmp/structura-world-benchmark.json'))
    args = parser.parse_args()
    faulthandler.enable()
    faulthandler.dump_traceback_later(180, exit=True)
    app = QApplication([])
    with TemporaryDirectory(prefix='structura-world-benchmark-') as temporary:
        root = Path(temporary)
        os.environ['STRUCTURA_EDIT_DATA'] = str(root / 'data')
        world = root / 'world'
        shutil.copytree(args.world, world, ignore=shutil.ignore_patterns('.structura', 'session.lock'))
        window = EditorWindow(off_screen=not args.visible, cache_dir=root / 'maps', world_radius=args.radius)
        window.setWindowTitle('Structura · world benchmark · closes automatically')
        window.resize(1380, 880)
        window.show()
        report = dict(radius=args.radius, visible=args.visible, stages={})
        try:
            for name, action in (('open', lambda: window.sources.open_path(world)),
                                 ('refresh', window.world.refresh), ('refresh_again', window.world.refresh)):
                report['stages'][name] = measure(window, action)
                print(name, report['stages'][name], flush=True)
            session = window.document.session
            position = next(p for p in session.positions() if session.state_at(p) == 'minecraft:stone')
            session.apply(session.set_block(position, 'minecraft:gold_block'))
            report['stages']['save'] = measure(window, window.sources.save_dialog)
            assert not window.document.session.dirty
            report['blocks'] = len(window.document.session._document.source.present)
            report['flight'] = flight(window, args.flight_seconds)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2))
            print(json.dumps(report, indent=2), flush=True)
        finally:
            window.tasks.close()
            window.exit.approved = True
            window.document.load(None)
            window.close()
            app.processEvents()
    faulthandler.cancel_dump_traceback_later()


if __name__ == '__main__':
    main()
