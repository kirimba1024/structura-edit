from concurrent.futures import Future

import numpy as np
from PySide6.QtGui import QImage

from structura_edit.map_cache_ui import MapCacheView
from structura_edit.map_canvas import MapCanvas
from structura_edit.map_projection import VIEWS


def spec(**changes):
    return dict(path='atlas.sqlite', space='world', stamps={'region': 'revision'},
                slabs={view: view for view in VIEWS}, **changes)


def test_streamed_area_retains_matching_projection_tiles_and_invalidates_changes(qt_app, tmp_path):
    canvas = MapCanvas()
    cache = MapCacheView(canvas, tmp_path)
    try:
        first = spec()
        cache.set_source(first)
        image = QImage(4, 4, QImage.Format.Format_RGBA8888)
        canvas.tiles = {(view, -128, -128): image for view in VIEWS}
        moved = dict(first, slabs=dict(first['slabs'], north='new north', south='new south'))
        cache.set_source(moved)
        assert {key[0] for key in canvas.tiles} == {'top', 'bottom', 'west', 'east'}
        cache.set_source(dict(moved, stamps={'region': 'edited'}))
        assert not canvas.tiles
        canvas.tiles = {('top', 0, 0): image}
        cache.set_source(dict(moved, space='other world'))
        assert not canvas.tiles
    finally:
        cache.close()
        canvas.deleteLater()


def test_completed_tiles_survive_camera_motion_while_next_area_is_requested(qt_app, tmp_path):
    canvas = MapCanvas()
    cache = MapCacheView(canvas, tmp_path)
    cache.timer.stop()
    try:
        cache.spec = spec()
        cache.current = cache.spec, {'top': (0, 0, 128, 128)}, {'top': 1}
        cache.pending = cache.spec, {'top': (128, 0, 256, 128)}, {'top': 1}
        cache.future = Future()
        cache.future.set_result({('top', 0, 0): np.full((4, 4, 4), 255, np.uint8)})
        started = []
        cache.executor.shutdown()
        from types import SimpleNamespace

        cache.executor = SimpleNamespace(submit=lambda *args: started.append(args) or Future(), shutdown=lambda **kwargs: None)
        cache.poll()
        assert ('top', 0, 0) in canvas.tiles
        assert started[0][2] == {'top': (128, 0, 256, 128)}
    finally:
        cache.close()
        canvas.deleteLater()
