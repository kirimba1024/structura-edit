import threading
import time

import numpy as np
import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QPointF
from PySide6.QtTest import QTest

from structura_edit.map_canvas import MapCanvas
from structura_edit.map_cache_ui import MapCacheView


def wait_for(condition):
    end = time.monotonic() + 3
    while not condition() and time.monotonic() < end:
        QTest.qWait(10)
    assert condition(), "Map request did not finish"


@pytest.mark.parametrize("action", ["close_source", "replace_source", "pan_back", "same_source"])
def test_slow_cache_read_respects_the_latest_source_and_view(qt_app, tmp_path, monkeypatch, action):
    started, release = threading.Event(), threading.Event()
    calls = []
    def read(spec, areas, scales):
        calls.append(spec["space"])
        if len(calls) == 1:
            started.set()
            assert release.wait(3)
        color = (100, 0, 0, 255) if spec["space"] == "first" else (0, 100, 0, 255)
        return {("top", 0, 0): np.full((128, 128, 4), color, dtype=np.uint8)}
    monkeypatch.setattr("structura_edit.map_cache_ui.read_tiles", read)
    canvas = MapCanvas()
    canvas.resize(600, 400)
    canvas.layout.large = True
    cache = MapCacheView(canvas, tmp_path)
    try:
        cache.set_source({"space": "first"})
        wait_for(started.is_set)
        if action == "close_source":
            cache.set_source(None)
        elif action == "replace_source":
            cache.set_source({"space": "second"})
        elif action == "same_source":
            cache.set_source({"space": "first"})
        else:
            canvas.layout.pan("top", QPointF(1000, 0))
            canvas.view_changed.emit()
            canvas.layout.pan("top", QPointF(-1000, 0))
            canvas.view_changed.emit()
        release.set()
        wait_for(lambda: not cache.timer.isActive())
        if action == "close_source":
            assert not canvas.tiles
        else:
            color = next(iter(canvas.tiles.values())).pixelColor(0, 0)
            assert color.green() == (100 if action == "replace_source" else 0)
        assert calls == (["first", "second"] if action == "replace_source" else ["first"])
        if action == "same_source":
            images = canvas.tiles.copy()
            cache.set_source({"space": "first"})
            assert canvas.tiles == images and not cache.timer.isActive()
    finally:
        release.set()
        cache.close()
        canvas.close()
        canvas.deleteLater()
