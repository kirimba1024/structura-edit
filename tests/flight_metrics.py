from math import isfinite
from time import perf_counter

import numpy as np
from PySide6.QtCore import QTimer, Qt


def distribution(values):
    return dict(zip(('mean', 'p50', 'p95', 'p99', 'p99_9', 'max'),
                    map(float, (np.mean(values), *np.percentile(values, (50, 95, 99, 99.9, 100)))))) if len(values) else {}


class FlightMetrics:
    def __init__(self, plotter, target_hz=60):
        if not isfinite(target_hz) or target_hz <= 0:
            raise ValueError("Target frequency must be finite and positive")
        self.plotter = plotter
        self.budget = 1000 / target_hz
        self.epoch = perf_counter()
        self.frames, self.renders, self.beats = [], [], [self.epoch]
        self.render_times = []
        self.started = None
        self.camera = self.camera_state()
        self.finished = None
        self.observers = (plotter.render_window.AddObserver('StartEvent', self.start),
                          plotter.render_window.AddObserver('EndEvent', self.end))
        self.timer = QTimer()
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(lambda: self.beats.append(perf_counter()))
        self.timer.start(5)

    def camera_state(self):
        camera = self.plotter.camera
        return tuple(camera.position), tuple(camera.focal_point), tuple(camera.up)

    def start(self, *_):
        self.started = perf_counter()

    def end(self, *_):
        if self.started is None:
            return
        now = perf_counter()
        self.renders.append((now - self.started) * 1000)
        self.render_times.append(now)
        self.started = None
        camera = self.camera_state()
        if camera != self.camera:
            self.frames.append(now)
            self.camera = camera

    def finish(self):
        if self.finished is not None:
            return self.finished
        stopped = perf_counter()
        self.timer.stop()
        for observer in self.observers:
            self.plotter.render_window.RemoveObserver(observer)
        intervals = np.diff(self.frames) * 1000
        gaps = np.diff([*self.beats, stopped]) * 1000
        self.finished = dict(frames=len(self.frames), renders=len(self.renders),
                    fps=float(1000 / np.mean(intervals)) if len(intervals) else 0,
                    seconds=stopped - self.epoch,
                    completed_motion_fps=len(self.frames) / (stopped - self.epoch) if stopped > self.epoch else 0,
                    first_motion_ms=(self.frames[0] - self.epoch) * 1000 if self.frames else None,
                    last_motion_gap_ms=(stopped - self.frames[-1]) * 1000 if self.frames else None,
                    frame_interval_count=len(intervals),
                    frame_ms=distribution(intervals), render_ms=distribution(self.renders), gui_gap_ms=distribution(gaps),
                    frame_budget_ms=self.budget, frames_over_budget=int(np.count_nonzero(intervals > self.budget)),
                    frames_over_double_budget=int(np.count_nonzero(intervals > 2 * self.budget)))
        return self.finished

    def samples(self):
        return dict(motion_frame_ms=[(time - self.epoch) * 1000 for time in self.frames],
                    render_end_ms=[(time - self.epoch) * 1000 for time in self.render_times],
                    render_duration_ms=self.renders,
                    heartbeat_ms=[(time - self.epoch) * 1000 for time in self.beats])
