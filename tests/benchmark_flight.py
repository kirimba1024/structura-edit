import argparse
import json
import time
from pathlib import Path

import numpy as np
from PySide6.QtCore import QEvent, QEventLoop, QPointF, QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from smoke_gui import settle
from structura_edit.ui import EditorWindow


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    parser.add_argument("--world-radius", type=int, default=1)
    parser.add_argument("--close", action="store_true")
    parser.add_argument("--ghost", action="store_true")
    parser.add_argument("--visible", action="store_true")
    parser.add_argument("--output", default="/private/tmp/structura-flight.json")
    args = parser.parse_args()
    app = QApplication([])
    window = EditorWindow(off_screen=not args.visible, cache_dir=Path(args.output).with_suffix(".cache"), world_radius=args.world_radius)
    window.navigation.mouse_look.capture = False
    window.show()
    try:
        window.sources.open_path(args.path)
        settle(window)
        window.navigation.stop()
        window.fit_scene()
        if args.close:
            center = np.asarray(window.document.session.size) / 2
            window.plotter.camera.position = center + np.array((0.2, 0.25, 0.85)) * max(window.document.session.size)
            window.plotter.camera.focal_point = center
        if args.ghost:
            upper = tuple(max(1, value // 2) for value in window.document.session.size)
            window.selection_actions.set_bounds((0, 0, 0), upper)
            window.placement.start("duplicate")
            settle(window)
            window.placement.set_position((2, 1, 2))
        frames = []
        completed = []
        durations = []
        started = [0.0]
        def start(*_):
            started[0] = time.perf_counter()
        def end(*_):
            now = time.perf_counter()
            completed.append(now)
            durations.append(now - started[0])
        window.plotter.render_window.AddObserver("StartEvent", start)
        window.plotter.render_window.AddObserver("EndEvent", end)
        window.plotter.setFocus()
        window.navigation.start_fly()
        window.navigation.speed = 1
        QTest.keyPress(window.plotter, Qt.Key.Key_W)
        QTest.keyPress(window.plotter, Qt.Key.Key_D)
        motion = QTimer(window)
        motion.setTimerType(Qt.TimerType.PreciseTimer)
        def move():
            now = time.perf_counter()
            frames.append(now)
            window.navigation.mouse_look.pending += QPointF(1.5, 0.1)
        motion.timeout.connect(move)
        motion.start(16)
        loop = QEventLoop()
        QTimer.singleShot(5000, loop.quit)
        loop.exec()
        motion.stop()
        window.navigation.stop()
        intervals = np.diff(frames)
        actual = np.diff(completed)
        report = dict(completed_frames=len(completed), rendered_fps=float(1 / actual.mean()) if len(actual) else 0,
                      actual_render_ms_mean=float(np.mean(durations) * 1000) if durations else 0,
                      blocks=len(window.document.session._document.source.present), actors=len(window.scene.actors),
                      viewport=list(window.plotter.render_window.GetSize()), frames=len(frames),
                      fps=float(1 / intervals.mean()), frame_ms_p95=float(np.percentile(intervals, 95) * 1000),
                      actual_render_ms_p95=float(np.percentile(durations, 95) * 1000) if durations else 0,
                      geometry_bytes=sum(window.scene.section_bytes.values()))
        Path(args.output).write_text(json.dumps(report, indent=2))
        print(json.dumps(report), flush=True)
    finally:
        window.document.load(None)
        window.close()
        window.deleteLater()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()


if __name__ == "__main__":
    main()
