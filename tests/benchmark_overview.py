import argparse
from collections import Counter
import json
import os
from pathlib import Path
import subprocess
from time import perf_counter

import numpy as np
from PySide6.QtCore import QEventLoop, QTimer, Qt
from PySide6.QtWidgets import QApplication

from smoke_overview import wait_until
from structura_core.world_terrain import terrain_stamp
from structura_edit.ui import EditorWindow


def memory(window):
    processes = [window.tasks.worker._process, window.overview.worker._process]
    pids = [os.getpid(), *(process.pid for process in processes if process is not None)]
    result = subprocess.run(["ps", "-o", "rss=", "-p", ",".join(map(str, pids))], capture_output=True, text=True, check=True)
    return sum(int(value) for value in result.stdout.split()) * 1024


def measure(window, action, ready, timeout=1800):
    beats, samples = [perf_counter()], []
    heartbeat, monitor = QTimer(), QTimer()
    heartbeat.setTimerType(Qt.TimerType.PreciseTimer)
    heartbeat.timeout.connect(lambda: beats.append(perf_counter()))
    def sample():
        samples.append(memory(window))
        print(window.overview.progress.label.text(), "rss", samples[-1], flush=True)
    monitor.timeout.connect(sample)
    heartbeat.start(16)
    monitor.start(5000)
    start = perf_counter()
    try:
        action()
        wait_until(ready, timeout)
        window.plotter._render()
    finally:
        heartbeat.stop()
        monitor.stop()
    gaps = np.diff([*beats, perf_counter()]) * 1000
    return dict(seconds=perf_counter() - start, gui_gap_p95_ms=float(np.percentile(gaps, 95)),
                gui_gap_max_ms=float(max(gaps)), rss_gui_workers_bytes=memory(window),
                sampled_rss_max_bytes=max(samples, default=memory(window)))


def flight(window, seconds=4):
    starts, ends, durations = [], [], []
    render_window = window.plotter.render_window
    def finished(*args):
        if starts:
            ends.append(perf_counter())
            durations.append((ends[-1] - starts[-1]) * 1000)
    observers = (render_window.AddObserver("StartEvent", lambda *args: starts.append(perf_counter())),
                 render_window.AddObserver("EndEvent", finished))
    loop, timer = QEventLoop(), QTimer()
    timer.setTimerType(Qt.TimerType.PreciseTimer)
    start = perf_counter()
    position = np.asarray(window.plotter.camera.position)
    focus = tuple(window.plotter.camera.focal_point)
    def step():
        phase = (perf_counter() - start) / 3
        window.plotter.camera.position = position + (np.sin(phase) * 10, np.sin(phase / 2) * 3, (np.cos(phase) - 1) * 10)
        window.plotter.camera.focal_point = focus
        window.camera.needs_render = True
        window.camera.render()
    timer.timeout.connect(step)
    timer.start(16)
    QTimer.singleShot(round(seconds * 1000), loop.quit)
    loop.exec()
    timer.stop()
    for observer in observers:
        render_window.RemoveObserver(observer)
    intervals = np.diff(ends) * 1000
    return dict(frames=len(ends), renders_per_second=float(1000 / np.mean(intervals)),
                frame_p95_ms=float(np.percentile(intervals, 95)), frame_p99_ms=float(np.percentile(intervals, 99)),
                render_mean_ms=float(np.mean(durations)), render_p95_ms=float(np.percentile(durations, 95)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("world", type=Path)
    parser.add_argument("--radius", type=int, default=6)
    parser.add_argument("--output", type=Path, default=Path("/private/tmp/structura-overview-benchmark.json"))
    parser.add_argument("--reuse", action="store_true")
    parser.add_argument("--flight-seconds", type=float, default=4)
    args = parser.parse_args()
    app = QApplication([])
    window = EditorWindow(off_screen=False, world_radius=args.radius, cache_dir=args.output.with_suffix(".maps"))
    window.setWindowTitle("Structura · overview benchmark · closes automatically")
    window.resize(1380, 880)
    window.show()
    overview = window.overview
    stamp = terrain_stamp(args.world / "region")
    report = dict(world=str(args.world), radius=args.radius, stages={})
    def settled():
        return (overview.snapshot is not None and overview.satisfied == overview._target()
                and not overview.worker.busy and not overview.uploads)
    def save():
        args.output.write_text(json.dumps(report, indent=2))
    try:
        report["stages"]["open"] = measure(window, lambda: window.sources.open_path(args.world),
                                              lambda: window.world.active and window.views.ready and not window.tasks.busy)
        window.navigation.stop()
        window.navigation.freelook = False
        report["stages"]["prepare"] = measure(window, (lambda: None) if args.reuse else overview.build, settled)
        snapshot = overview.snapshot
        report["snapshot"] = {**snapshot["metadata"], "path": snapshot["path"],
                              "disk_bytes": Path(snapshot["path"]).stat().st_size}
        save()
        report["stages"]["fit"] = measure(window, overview.fit_world, settled)
        report["fit_lod_counts"] = dict(Counter(tile[0] for _, (_, tiles) in overview.scene.visible for tile in tiles))
        window.minimap.world_map.fit()
        window.plotter._render()
        report["fit_camera"] = dict(position=list(window.plotter.camera.position), target=list(window.plotter.camera.focal_point),
                                    direction=list(window.plotter.camera.direction), bounds=list(window.plotter.bounds))
        report["fit_actors"] = dict(visible=sum(actor.GetVisibility() for entry in overview.scene.entries.values() for actor in entry[0]),
                                    total=sum(len(entry[0]) for entry in overview.scene.entries.values()))
        window.plotter.screenshot(str(args.output.with_name(args.output.stem + "-3d.png")))
        save()
        window.grab().save(str(args.output.with_suffix(".png")))
        generation = overview.intent.generation
        for step in range(30):
            window.camera.look(10, 0)
            window.camera.render()
            overview.tick()
        assert generation == overview.intent.generation
        report["rotation_starts_no_jobs"] = True
        overview.fit_world()
        wait_until(settled, 120)
        window.plotter._render()
        report["flight_camera"] = list(window.plotter.camera.position), list(window.plotter.camera.focal_point)
        report["flight"] = flight(window, args.flight_seconds)
        lower, upper = snapshot["metadata"]["bounds"]
        destinations = [(lower[0] + 40, upper[1] + 20, lower[2] + 40),
                        (upper[0] - 40, upper[1] + 20, upper[2] - 40)]
        original = window.document.session
        def teleport():
            for destination in destinations:
                window.move_camera(tuple(p - o for p, o in zip(destination, original.origin)))
        report["stages"]["teleport"] = measure(window, teleport, lambda: overview.intent.destination is None and settled())
        assert window.document.session is original and np.allclose(window.world.camera_position(), destinations[-1])
        report["latest_teleport_wins"] = True
        report["visible_tiles"] = len(overview.scene.visible)
        report["geometry_bytes"] = sum(entry[2] for entry in overview.scene.entries.values())
        report["overview_actors"] = sum(len(entry[0]) for entry in overview.scene.entries.values())
        report["viewport"] = list(window.plotter.render_window.GetSize())
        report["issues"] = window.issues
        assert terrain_stamp(args.world / "region") == stamp
        report["source_unchanged"] = True
        save()
        print(json.dumps(report, indent=2), flush=True)
    finally:
        window.document.load(None)
        window.close()
        app.processEvents()


if __name__ == "__main__":
    main()
