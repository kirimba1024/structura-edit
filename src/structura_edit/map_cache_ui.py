from concurrent.futures import ThreadPoolExecutor
from math import ceil, floor, log2
from pathlib import Path
import sqlite3

from PySide6.QtCore import QObject, QStandardPaths, QTimer
from PySide6.QtGui import QImage

from .map_cache import TILE_SIZE, read_tiles
from .map_images import MAP_TEXTURE_SIZE
from .map_projection import VIEWS


class MapCacheView(QObject):
    def __init__(self, canvas, directory=None):
        super().__init__(canvas)
        root = Path(directory) if directory else Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericCacheLocation)) / "structura-edit"
        self.path = root / "atlas-v1.sqlite"
        self.canvas = canvas
        self.spec = None
        self.pending = None
        self.current = None
        self.future = None
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="map-cache")
        self.timer = QTimer(self)
        self.timer.setInterval(80)
        self.timer.timeout.connect(self.poll)
        canvas.view_changed.connect(self.request)

    def set_source(self, spec):
        self.spec = spec
        self.current = None
        self.pending = None
        self.canvas.tiles.clear()
        self.request()

    def request(self):
        if self.spec is None or not self.canvas.layout.large:
            self.pending = None
            return
        views = (self.canvas.layout.focused,) if self.canvas.layout.focused else VIEWS
        areas = {}
        scales = {}
        for view in views:
            rect = self.canvas.layout.area(view)
            areas[view] = (floor(rect.left() / TILE_SIZE) * TILE_SIZE, floor(rect.top() / TILE_SIZE) * TILE_SIZE,
                           ceil(rect.right() / TILE_SIZE) * TILE_SIZE, ceil(rect.bottom() / TILE_SIZE) * TILE_SIZE)
            pixels = self.canvas.tile_rect(view).width() * self.canvas.devicePixelRatioF() / rect.width()
            scales[view] = min(MAP_TEXTURE_SIZE, 2 ** ceil(log2(max(1, pixels))))
        request = self.spec, areas, scales
        self.pending = request if request != self.current or self.future is not None else None
        if self.pending is not None and not self.timer.isActive():
            self.timer.start()

    def poll(self):
        if self.future is not None:
            if not self.future.done():
                return
            try:
                pixels = self.future.result()
            except (OSError, ValueError, sqlite3.Error) as error:
                self.canvas.setToolTip(f"Map cache unavailable: {error}")
                pixels = {}
            self.future = None
            if self.current is not None and self.current == self.pending and self.spec == self.current[0]:
                self.canvas.tiles = {key: QImage(data.data, data.shape[1], data.shape[0], data.strides[0],
                                               QImage.Format.Format_RGBA8888).copy() for key, data in pixels.items()}
                self.canvas.update()
                self.pending = None
            else:
                self.current = None
        if self.pending is not None and self.pending != self.current:
            self.current = self.pending
            self.future = self.executor.submit(read_tiles, *self.current)
        if self.future is None:
            self.timer.stop()

    def close(self):
        self.timer.stop()
        self.pending = None
        self.executor.shutdown(wait=False, cancel_futures=True)
