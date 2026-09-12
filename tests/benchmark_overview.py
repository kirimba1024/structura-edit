import argparse
from collections import Counter
import cProfile
import json
from math import isfinite
import os
from pathlib import Path
import subprocess
from time import perf_counter

import numpy as np
from PySide6.QtCore import QEventLoop, QTimer, Qt
from PySide6.QtWidgets import QApplication

from benchmark_runtime import NativeSession, isolated_data, scene_resources
from flight_metrics import FlightMetrics, distribution
from flight_paths import load_paths
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
    return dict(seconds=perf_counter() - start, gui_gap_ms=distribution(gaps), gui_gap_p95_ms=float(np.percentile(gaps, 95)),
                gui_gap_max_ms=float(max(gaps)), rss_gui_workers_bytes=memory(window),
                sampled_rss_max_bytes=max(samples, default=memory(window)))


def move_camera(window, position, target):
    origin = window.document.session.origin
    window.camera.translate(np.asarray(position) - origin - window.plotter.camera.position)
    window.plotter.camera.SetFocalPoint(*(np.asarray(target) - origin))
    window.plotter.camera.up = (0, 1, 0)
    window.camera.render()


def flight(window, seconds, *, target_hz, tick_ms, path=None, samples_path=None, profile_path=None):
    resources = scene_resources(window)
    rss = memory(window)
    metrics = FlightMetrics(window.plotter, target_hz)
    loop, timer = QEventLoop(), QTimer()
    timer.setTimerType(Qt.TimerType.PreciseTimer)
    start = perf_counter()
    position = np.asarray(window.plotter.camera.position)
    focus = tuple(window.plotter.camera.focal_point)
    def step():
        elapsed = perf_counter() - start
        if path is not None:
            move_camera(window, *path.pose(elapsed, seconds))
        else:
            phase = elapsed / 3
            target = position + (np.sin(phase) * 10, np.sin(phase / 2) * 3, (np.cos(phase) - 1) * 10)
            window.camera.translate(target - window.plotter.camera.position)
            window.plotter.camera.SetFocalPoint(*focus)
            window.camera.render()
    timer.timeout.connect(step)
    timer.start(tick_ms)
    deadline = QTimer()
    deadline.setSingleShot(True)
    deadline.setTimerType(Qt.TimerType.PreciseTimer)
    deadline.timeout.connect(loop.quit)
    deadline.start(round(seconds * 1000))
    profile = cProfile.Profile() if profile_path is not None else None
    try:
        if profile is not None:
            profile.enable()
        loop.exec()
    finally:
        if profile is not None:
            profile.disable()
            profile.dump_stats(str(profile_path))
        timer.stop()
        deadline.stop()
        result = metrics.finish()
    if samples_path is not None:
        samples_path.write_text(json.dumps(metrics.samples()))
    return dict(result, motion_timer_ms=tick_ms, resources_before=resources, resources_after=scene_resources(window),
                rss_before_bytes=rss, rss_after_bytes=memory(window), samples=str(samples_path) if samples_path else None)


def run(args, root, report):
    app = QApplication([])
    window = EditorWindow(off_screen=False, world_radius=args.radius, cache_dir=root / "maps")
    window.navigation.freelook = False
    window.setWindowTitle("Structura · overview benchmark · closes automatically")
    window.resize(1380, 880)
    window.show()
    overview = window.overview
    stamp = terrain_stamp(args.world / "region")
    native = None
    def settled():
        return (overview.snapshot is not None and overview.satisfied == overview._target()
                and not overview.worker.busy and not overview.uploads and overview.installation is None)
    def save():
        args.output.write_text(json.dumps(report, indent=2))
    try:
        native = NativeSession(window, args.viewport, require_active=not args.diagnostic)
        report["environment"] = native.record()
        report["stages"]["open"] = measure(window, lambda: window.sources.open_path(args.world),
                                              lambda: window.world.active and window.views.ready and not window.tasks.busy)
        report["stages"]["open"]["viewport"] = list(window.plotter.render_window.GetSize())
        native.fit_viewport()
        window.navigation.stop()
        window.navigation.freelook = False
        report["stages"]["prepare"] = measure(window, (lambda: None) if args.reuse else overview.build, settled)
        native.check()
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
        report["flight"] = flight(window, args.flight_seconds, target_hz=args.target_hz, tick_ms=args.tick_ms,
                                  samples_path=args.output.with_name(args.output.stem + "-overview-samples.json"),
                                  profile_path=args.output.with_name(args.output.stem + "-overview.prof") if args.profile else None)
        native.check()
        save()
        report["flights"] = {}
        for path in args.paths:
            record = dict(path=path.record(), seconds=args.flight_seconds)
            report["flights"][path.name] = record
            record["setup"] = measure(window, lambda: move_camera(window, path.position, path.target), settled)
            window.plotter.screenshot(str(args.output.with_name(args.output.stem + f"-{path.name}-3d.png")))
            record["measurement"] = flight(window, args.flight_seconds, target_hz=args.target_hz, tick_ms=args.tick_ms,
                                           path=path, samples_path=args.output.with_name(args.output.stem + f"-flight-{path.name}-samples.json"),
                                           profile_path=args.output.with_name(args.output.stem + f"-flight-{path.name}.prof") if args.profile else None)
            record["settle"] = measure(window, lambda: None, settled)
            native.check()
            save()
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
        report["geometry_bytes"] = sum(entry[1] for entry in overview.scene.entries.values())
        report["overview_actors"] = sum(len(entry[0]) for entry in overview.scene.entries.values())
        report["viewport"] = list(window.plotter.render_window.GetSize())
        report["issues"] = window.issues
        assert not window.issues, window.issues
        assert terrain_stamp(args.world / "region") == stamp
        report["source_unchanged"] = True
        native.check()
        report["environment"] = native.record()
        report["status"] = "diagnostic" if args.diagnostic or args.profile else "passed"
        save()
    finally:
        if native is not None:
            report["environment"] = native.record()
            native.close()
        report["source_unchanged"] = terrain_stamp(args.world / "region") == stamp
        window.document.load(None)
        window.close()
        app.processEvents()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("world", type=Path)
    parser.add_argument("--radius", type=int, default=6)
    parser.add_argument("--output", type=Path, default=Path("/private/tmp/structura-overview-benchmark.json"))
    parser.add_argument("--reuse", action="store_true")
    parser.add_argument("--cache-source", type=Path)
    parser.add_argument("--flight-seconds", type=float, default=30)
    parser.add_argument("--target-hz", type=int, choices=(60, 120), default=60)
    parser.add_argument("--tick-ms", type=int, default=16)
    parser.add_argument("--viewport", type=int, nargs=2, default=(2760, 1600), metavar=("WIDTH", "HEIGHT"))
    parser.add_argument("--paths", type=Path)
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--diagnostic", action="store_true", help="Allow an inactive window; never counts as a foreground FPS reference")
    args = parser.parse_args()
    if not isfinite(args.flight_seconds) or not 1 <= args.flight_seconds <= 120:
        parser.error("--flight-seconds must be between 1 and 120")
    if not 1 <= args.tick_ms <= 100 or min(args.viewport) < 64 or not 0 <= args.radius <= 32:
        parser.error("Use a 1–100 ms timer, a viewport of at least 64 pixels and a 0–32 chunk radius")
    try:
        args.paths = load_paths(args.paths) if args.paths else []
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.error(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = dict(world=str(args.world), radius=args.radius, stages={}, status="running", target_hz=args.target_hz,
                  flight_seconds=args.flight_seconds, motion_timer_ms=args.tick_ms, diagnostic=args.diagnostic, profiled=args.profile)
    try:
        with isolated_data(args.world, args.reuse, args.cache_source) as (root, seeded):
            report["cache_seed"] = seeded
            run(args, root, report)
    except Exception as error:
        report["status"] = "failed"
        report["error"] = str(error)
        raise
    finally:
        if report["status"] == "running":
            report["status"] = "interrupted"
        args.output.write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
