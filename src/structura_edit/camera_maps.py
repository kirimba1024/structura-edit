from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, QTimer, Signal

from .camera_map_render import context_key as context_key, render_camera_maps as render_camera_maps
from .map_projection import camera_cut
from .map_detail import detail_areas


class CameraMaps(QObject):
    failed = Signal(str)
    mode_changed = Signal(bool)

    def __init__(self, canvas, cache):
        super().__init__(canvas)
        self.canvas, self.cache = canvas, cache
        self.context = self.previous = self.future = self.shown = None
        self.active = True
        self.sliced = False
        self.automatic = False
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="camera-maps")
        self.timer = QTimer(self)
        self.timer.setInterval(80)
        self.timer.timeout.connect(self.poll)
        canvas.view_changed.connect(self.update)

    def target(self):
        if self.context is None:
            return None
        cut = camera_cut(self.canvas.position, self.context.state.size) if self.sliced or self.automatic else None
        return context_key(self.context), cut, self.canvas.layout.large, detail_areas(self.canvas), self.automatic, (camera_cut(self.canvas.position, self.context.state.size)[1] if self.canvas.dimension else None)

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
        self.canvas.set_details({})

    def poll(self):
        if self.future is not None and self.future.done():
            future, self.future = self.future, None
            target = self.running
            try:
                previous, images, atlas, notice, details, cut, cave_y = future.result()
                if self.context is not None and target[0] == context_key(self.context):
                    self.previous = previous
                    if self.active and target == self.target():
                        self.canvas.set_images(images)
                        self.canvas.set_details(details)
                        self.canvas.map_cut = cut
                        self.canvas.cave_y = cave_y
                        self.mode_changed.emit(cut is not None)
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
            self.future = self.executor.submit(render_camera_maps, self.context, target[1], target[2], self.previous, self.cache.path, target[3], target[4], target[5])
        if not self.busy:
            self.timer.stop()

    def close(self):
        self.active = False
        self.timer.stop()
        self.executor.shutdown(wait=False, cancel_futures=True)
