from concurrent.futures import ThreadPoolExecutor
from math import cos, radians, sin

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QToolButton, QVBoxLayout, QWidget

from .appearance import GRID, SCENE_BACKGROUND
from .controls import CellLabel
from .inspection import InspectionBuilder, block_details, entity_details, inspection_preview_key
from .inspection_scene import InspectionScene
from .section_cache import SectionCache
from .viewport import SceneView


class InspectionCard(QWidget):
    completed = Signal(object)

    def __init__(self, plotter, minimap, inspect):
        super().__init__(plotter)
        self.plotter, self.minimap = plotter, minimap
        self.setObjectName("minimap")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setFixedWidth(288)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(GRID, GRID, GRID, GRID)
        self.layout.setSpacing(0)
        self.title = CellLabel()
        self.layout.addWidget(self.title)
        self.facts = [CellLabel() for _ in range(5)]
        for label in self.facts:
            self.layout.addWidget(label)
        self.note = CellLabel()
        self.layout.addWidget(self.note)
        self.preview = SceneView(self, axes=False)
        self.scene = InspectionScene(self.preview)
        self.preview.setFixedHeight(128)
        self.preview.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.preview.set_background(SCENE_BACKGROUND)
        self.preview.enable_depth_peeling(number_of_peels=4)
        self.layout.insertWidget(1, self.preview)
        self.preview.hide()
        self.buttons = QWidget()
        row = QHBoxLayout(self.buttons)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(GRID)
        self.rotate = QToolButton(text="Pause", checkable=True)
        self.rotate.setToolTip("Pause or resume the rotating preview")
        self.rotate.clicked.connect(lambda paused: self.rotate.setText("Rotate" if paused else "Pause"))
        self.inspect = QToolButton(text="Inspect…")
        self.inspect.setToolTip("Inspect all materials, block data and entities in the selection. Open an object for its inventory and NBT.")
        self.inspect.clicked.connect(inspect)
        row.addWidget(self.rotate, 1)
        row.addWidget(self.inspect, 1)
        self.layout.addWidget(self.buttons)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="inspection")
        self.builder = InspectionBuilder()
        self.cache = SectionCache(limit=16 * 1024 ** 2, max_entries=32)
        self.completed.connect(self._receive, Qt.ConnectionType.QueuedConnection)
        self.closed = False
        self.future = None
        self.key = self.ready_key = self.running_key = None
        self.preview_key = self.running_cache_key = None
        self.hover_key = None
        self.context = None
        self.allowed = False
        self.angle = 35
        self.radius = 5
        self.center = (0, 0, 0)
        self.has_geometry = False
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.tick)
        self.timer.start()
        plotter.resized.connect(self.reposition)
        minimap.expanded_changed.connect(self.reposition)
        self.hide()

    def set_context(self, session, selection, keys, assets, *, visible):
        self.allowed = visible and session is not None
        key = (session._id, session._state_id, session.revision, selection if not keys else None, tuple(sorted(keys)), assets) if session and (selection or keys) else None
        self.context = (session, selection, tuple(keys), assets) if key else None
        if key != self.key:
            self.hover_key = None
            self.key = key
            self.preview_key = inspection_preview_key(session, selection, keys, assets) if key else None
            self.ready_key = None
            if key is None:
                self.has_geometry = False
                self.preview.hide()
            if key:
                if keys:
                    if len(keys) == 1:
                        title, facts, detail, _ = entity_details(session, keys)
                    else:
                        title, facts, detail = f"{len(keys):,} entities", ["Reading entity details…"], ""
                elif selection.volume == 1:
                    title, facts, detail = block_details(session, selection.lower)
                else:
                    title, facts, detail = "Selection", ["Counting blocks…"], ""
                self.show_details(title, facts, detail)
                self.note.setText("Building preview…")
                self.note.show()
            self.buttons.setVisible(self.has_geometry)
        self.inspect.setVisible(bool(keys) or selection is not None)
        self.setVisible(self.allowed and key is not None)
        self.reposition()
        self._request()

    def hover(self, session, position=None, entity=None):
        if session is None:
            self.hide()
            return
        if self.key is not None or not self.allowed:
            return
        key = (session._id, session.revision, position, entity)
        if key == self.hover_key and self.isVisible():
            return
        self.hover_key = key
        if entity is not None:
            title, facts, detail, _ = entity_details(session, (entity,))
        elif position is not None:
            title, facts, detail = block_details(session, position)
        else:
            self.hide()
            return
        self.show_details(title, facts[:2], detail)
        self.note.hide()
        self.buttons.hide()
        if self.preview:
            self.preview.hide()
        self.show()
        self.reposition()

    def show_details(self, title, facts, detail):
        self.title.setText(title)
        self.title.setToolTip(detail or title)
        for index, label in enumerate(self.facts):
            label.setVisible(index < len(facts))
            label.setText(facts[index] if index < len(facts) else "")
        self.setToolTip("\n".join((title, *facts, detail)))

    def _request(self):
        if self.closed or not self.isVisible() or not self.context or self.ready_key == self.key:
            return
        cached = self.cache.get(self.preview_key or self.key)
        if cached is not None:
            self._install(cached)
        elif self.future is None:
            session, selection, keys, assets = self.context
            self.running_key = self.key
            self.running_cache_key = self.preview_key or self.key
            self.future = self.executor.submit(self.builder, session.fork(), selection, keys, assets)
            self.future.add_done_callback(self._completed)

    def _completed(self, future):
        if not self.closed:
            try:
                self.completed.emit(future)
            except RuntimeError:
                pass

    def _receive(self, future):
        if self.closed or future is not self.future:
            return
        key = self.running_key
        self.future = None
        try:
            result = future.result()
            self.cache.put(self.running_cache_key, dict(result, geometry_bytes=result["geometry"]["geometry_bytes"]))
            if key == self.key:
                self._install(result)
        except Exception as error:
            if key == self.key:
                self.ready_key = key
                self.has_geometry = False
                self.preview.hide()
                self.note.setText("Preview unavailable · see details")
                self.note.setToolTip(str(error))
                self.note.show()
                self.buttons.hide()
                self.reposition()
        self._request()

    def _install(self, result):
        self.ready_key = self.key
        if self.preview_key is None:
            self.show_details(result["title"], result["facts"], result["detail"])
        self.note.setText(result["note"])
        self.note.setToolTip("")
        self.note.setVisible(bool(result["note"]))
        self.install_geometry(result["geometry"])
        self.reposition()

    def tick(self):
        if self.isVisible() and self.window().isActiveWindow() and self.has_geometry and not self.rotate.isChecked():
            self.angle = (self.angle + 3) % 360
            self.update_camera()

    def install_geometry(self, data):
        self.has_geometry, self.center, self.radius = self.scene.show(self.preview_key or self.key, data)
        self.preview.setVisible(self.has_geometry)
        self.buttons.setVisible(self.has_geometry)
        if self.has_geometry:
            self.update_camera()
        else:
            self.note.setText("Empty selection")
            self.note.show()

    def update_camera(self):
        angle = radians(self.angle)
        x, y, z = self.center
        self.preview.camera_position = [(x + sin(angle) * self.radius, y + self.radius * .55, z + cos(angle) * self.radius), self.center, (0, 1, 0)]
        self.preview.reset_camera_clipping_range()
        self.preview.render()

    def reposition(self, *args):
        if not self.isVisible():
            return
        self.adjustSize()
        below = self.minimap.y() + self.minimap.height() + GRID if self.minimap.isVisible() else GRID
        fits = below + self.height() <= self.plotter.height() - 100
        self.move(max(GRID, self.minimap.x() + self.minimap.width() - self.width() - GRID) if fits else int(self.plotter.width() * .085) + GRID, below if fits else GRID)
        self.raise_()

    def shutdown(self):
        self.closed = True
        self.timer.stop()
        self.executor.shutdown(wait=False, cancel_futures=True)
        if self.preview:
            self.scene.clear()
            self.preview.close()
