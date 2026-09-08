from concurrent.futures import ThreadPoolExecutor
import sqlite3

from PySide6.QtCore import QObject, QTimer, Signal

from .map_images import MAX_MAP_PIXELS, MapRenderer
from .map_projection import camera_cut
from .resources import refresh_resources, resolve_assets


def context_key(request):
    state = request.state
    return state._id, state._state_id, state.origin, state.size, request.assets, request.height


def render_camera_maps(request, cut, large, previous, cache_path):
    from .map_cache import map_spec, store_maps

    key = context_key(request)
    if previous is None or previous[0] != key:
        refresh_resources(request.assets)
        renderer = MapRenderer(request.map_args()["source"], request.assets)
    else:
        renderer = previous[1]
    budget = MAX_MAP_PIXELS if large else min(MAX_MAP_PIXELS, max(256_000, sum(
        renderer.size[a] * renderer.size[b] * 2 for a, b in ((0, 1), (0, 2), (1, 2)))))
    images = renderer.images(cut=cut, max_pixels=budget)
    atlas, notice = None, ""
    if large and request.height.mode == "all":
        atlas = map_spec(request.state, resolve_assets(request.assets), cache_path, cut=cut)
        if atlas is not None:
            try:
                images, atlas = store_maps(atlas, images)
            except (OSError, ValueError, sqlite3.Error) as error:
                atlas, notice = None, f"Map cache unavailable: {error}"
    return (key, renderer), images, atlas, notice


class CameraMaps(QObject):
    failed = Signal(str)

    def __init__(self, canvas, cache):
        super().__init__(canvas)
        self.canvas, self.cache = canvas, cache
        self.context = self.previous = self.future = self.shown = None
        self.active = True
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="camera-maps")
        self.timer = QTimer(self)
        self.timer.setInterval(80)
        self.timer.timeout.connect(self.poll)

    def target(self):
        if self.context is None:
            return None
        return context_key(self.context), camera_cut(self.canvas.position, self.context.state.size), self.canvas.layout.large

    @property
    def busy(self):
        return self.future is not None or self.active and self.target() != self.shown

    def request(self, request):
        self.context = request
        self.update()

    def update(self):
        if self.busy and not self.timer.isActive():
            self.timer.start()

    def reset(self):
        self.context = self.previous = self.shown = None

    def poll(self):
        if self.future is not None and self.future.done():
            future, self.future = self.future, None
            target = self.running
            try:
                previous, images, atlas, notice = future.result()
                if self.context is not None and target[0] == context_key(self.context):
                    self.previous = previous
                    if self.active and target[2] == self.canvas.layout.large:
                        self.canvas.set_images(images)
                        self.canvas.map_cut = target[1]
                        self.cache.set_source(atlas)
                        if notice:
                            self.canvas.setToolTip(notice)
                        self.shown = target
            except Exception as error:
                if target == self.target():
                    self.shown = target
                    self.failed.emit(f"Map unavailable: {error}")
        target = self.target()
        if self.future is None and self.active and target is not None and target != self.shown:
            self.running = target
            self.future = self.executor.submit(render_camera_maps, self.context, target[1], target[2], self.previous, self.cache.path)
        if not self.busy:
            self.timer.stop()

    def close(self):
        self.active = False
        self.timer.stop()
        self.executor.shutdown(wait=False, cancel_futures=True)
