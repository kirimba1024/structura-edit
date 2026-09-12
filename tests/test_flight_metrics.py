from types import SimpleNamespace

import pytest

import flight_metrics
from flight_metrics import FlightMetrics


@pytest.fixture
def measured(monkeypatch):
    clock = [0.0]
    observers = {}
    window = SimpleNamespace(AddObserver=lambda name, callback: observers.setdefault(name, callback) and name,
                             RemoveObserver=lambda name: observers.pop(name))
    timer = SimpleNamespace(timeout=SimpleNamespace(connect=lambda callback: None),
                            setTimerType=lambda value: None, start=lambda value: None, stop=lambda: None)
    monkeypatch.setattr(flight_metrics, "perf_counter", lambda: clock[0])
    monkeypatch.setattr(flight_metrics, "QTimer", lambda: timer)
    plotter = SimpleNamespace(render_window=window, camera=SimpleNamespace(position=(0, 0, 0), focal_point=(0, 0, 1), up=(0, 1, 0)))
    return FlightMetrics(plotter), clock, observers


def render(metrics, clock, start, end, position=None):
    clock[0] = start
    metrics.start()
    if position is not None:
        metrics.plotter.camera.position = position
    clock[0] = end
    metrics.end()


def test_repeated_static_renders_do_not_count_as_motion(measured):
    metrics, clock, observers = measured
    render(metrics, clock, 0.01, 0.015)
    render(metrics, clock, 0.02, 0.025, (1, 0, 0))
    render(metrics, clock, 0.03, 0.035)
    render(metrics, clock, 0.04, 0.045, (2, 0, 0))
    clock[0] = 0.1
    result = metrics.finish()
    assert result["frames"] == 2 and result["renders"] == 4
    assert result["fps"] == pytest.approx(50)
    assert result["completed_motion_fps"] == pytest.approx(20)
    assert result["first_motion_ms"] == pytest.approx(25)
    assert result["last_motion_gap_ms"] == pytest.approx(55)
    assert result["frame_interval_count"] == 1
    assert result["frames_over_budget"] == 1
    assert result["frames_over_double_budget"] == 0
    assert result["render_ms"]["max"] == pytest.approx(5)
    assert not observers
    assert metrics.finish() is result


def test_empty_measurement_and_unmatched_render_event(measured):
    metrics, clock, _ = measured
    clock[0] = 1
    metrics.end()
    result = metrics.finish()
    assert result["frames"] == result["renders"] == result["fps"] == 0
    assert result["first_motion_ms"] is None and result["last_motion_gap_ms"] is None
    assert result["frame_ms"] == result["render_ms"] == {}
    assert result["gui_gap_ms"]["max"] == 1000


def test_camera_roll_and_raw_samples(measured):
    metrics, clock, _ = measured
    metrics.plotter.camera.up = (1, 0, 0)
    render(metrics, clock, 0.01, 0.02)
    assert metrics.finish()["frames"] == 1
    assert metrics.samples()["motion_frame_ms"] == [20]
    assert metrics.samples()["render_end_ms"] == [20]
    assert metrics.samples()["render_duration_ms"] == [10]


@pytest.mark.parametrize("hz", (0, -1, float("inf"), float("nan")))
def test_invalid_frame_budget(hz):
    with pytest.raises(ValueError, match="frequency"):
        FlightMetrics(None, hz)
