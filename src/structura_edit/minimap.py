from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QStackedWidget, QToolButton, QVBoxLayout, QWidget

from .appearance import MAP_HEADER_HEIGHT
from .map_canvas import MapCanvas
from .map_cache_ui import MapCacheView
from .camera_maps import CameraMaps
from .navigation_keys import control_key
from .world_map import WorldMap


class MiniMap(QWidget):
    navigate = Signal(object)
    load_requested = Signal()
    expanded_changed = Signal(bool)
    large_changed = Signal(bool)

    def __init__(self, parent, *, cache_dir=None):
        super().__init__(parent)
        self._collapsed = False
        self.right_inset = 0
        self.setObjectName("minimap")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_LayoutOnEntireRect)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.canvas = MapCanvas()
        self.world_map = WorldMap()
        self.world_map.images_changed.connect(self._overview_images)
        self.canvas.view_changed.connect(self._overview_request)
        self.map_stack = QStackedWidget()
        self.map_stack.addWidget(self.canvas)
        self.map_stack.addWidget(self.world_map)
        self.cache = MapCacheView(self.canvas, cache_dir)
        self.maps = CameraMaps(self.canvas, self.cache)
        self.canvas.navigate.connect(self._navigate)
        self.header = self._button("", "Map projections", self._header_clicked)
        self.header.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.center = self._button("F · Center", "Center the map on the camera (F)", self.recenter)
        self.maps.automatic = True
        self.mode = self._button("Auto", "Auto chooses surface or cave from the camera surroundings. Click for Surface or Slices.", self.toggle_mode)
        self.maps.mode_changed.connect(self._mode_changed)
        self.expand = self._button("M +", "Expand map (M)", self.toggle_large)
        self.expand.setObjectName("mapExpand")
        self.world_mode = self._button("World", "Show the prepared world map", self._world_toggled)
        self.world_mode.setCheckable(True)
        self.world_mode.hide()
        row = QHBoxLayout()
        row.setSpacing(0)
        row.addWidget(self.header, 1)
        row.addWidget(self.center)
        row.addWidget(self.mode)
        row.addWidget(self.world_mode)
        row.addWidget(self.expand)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(row)
        self.radar = self._button("Entities: Auto", "Entity markers: Auto, Icons, Dots or Off", self.toggle_entities)
        layout.addWidget(self.radar)
        layout.addWidget(self.map_stack)
        self.load_here = self._button("Load here · F5", "Load a fresh area around the camera (F5). Your edits stay. Hatched map areas have no map data.", self.load_requested)
        self.load_here.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.load_here.hide()
        layout.addWidget(self.load_here)
        self.shortcut = QShortcut(QKeySequence("M"), parent)
        self.shortcut.setKeys([QKeySequence("M"), QKeySequence("Ь")])
        self.shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.shortcut.setAutoRepeat(False)
        self.shortcut.activated.connect(self.toggle_large)
        self._update_layout()
        self.hide()

    def _button(self, text, tip, callback):
        button = QToolButton()
        button.setText(text)
        button.setToolTip(tip)
        button.setAccessibleName(tip)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setFixedHeight(MAP_HEADER_HEIGHT)
        button.clicked.connect(callback)
        return button

    @property
    def large(self):
        return self.canvas.layout.large

    @property
    def collapsed(self):
        return self._collapsed and not self.large

    def set_collapsed(self, collapsed):
        self._collapsed = collapsed
        self._update_layout()

    def _header_clicked(self):
        if self.large:
            self.canvas.layout.focused = None
            self.canvas.view_changed.emit()
            self.canvas.update()
        else:
            self.set_collapsed(not self.collapsed)

    def toggle_large(self):
        if self.isVisible():
            self.set_large(not self.large)

    def toggle_entities(self):
        modes = ("Auto", "Icons", "Dots", "Off")
        self.canvas.entity_mode = modes[(modes.index(self.canvas.entity_mode) + 1) % len(modes)]
        self.radar.setText("Entities: " + self.canvas.entity_mode)
        self.canvas.update()

    def toggle_mode(self):
        if self.maps.automatic:
            self.maps.automatic = False
            self.maps.sliced = False
        elif not self.maps.sliced:
            self.maps.sliced = True
        else:
            self.maps.sliced = False
            self.maps.automatic = True
        self._mode_changed(self.maps.sliced)
        self.maps.update()

    def _mode_changed(self, cave):
        self.mode.setText(("Auto cave" if cave else "Auto") if self.maps.automatic else "Slices" if self.maps.sliced else "Surface")

    def set_large(self, large):
        if large == self.large:
            return
        self.canvas.layout.large = large
        if not large:
            self.canvas.map_cut = self.canvas.cave_y = None
            self.canvas.set_images({})
            self.maps.shown = None
        self.canvas.press = None
        self.canvas.unsetCursor()
        self._update_layout()
        self.large_changed.emit(large)
        (self if large else self.parentWidget()).setFocus(Qt.FocusReason.OtherFocusReason)
        self.canvas.view_changed.emit()

    def _update_layout(self):
        world = self.large and self.world_mode.isChecked()
        self.map_stack.setCurrentWidget(self.world_map if world else self.canvas)
        self.map_stack.setVisible(not self.collapsed)
        self.radar.setVisible(not self.collapsed and not world)
        self.load_here.setVisible(not self.collapsed and bool(self.canvas.dimension))
        self.header.setText("Map" if self.large else "MAP +" if self.collapsed else "MAP −")
        self.expand.setText("M ×" if self.large else "M +")
        self.expand.setToolTip("Close map (M / Escape)" if self.large else "Expand map (M)")
        self.center.setVisible(self.large)
        self.mode.setVisible(self.large and not self.world_mode.isChecked())
        self.world_mode.setVisible(self.large and self.world_map.snapshot is not None)
        self.maps.active = not self.collapsed and not world
        self.maps.update()
        self.reposition()
        self.expanded_changed.emit(not self.collapsed)

    def set_overview(self, snapshot):
        self.canvas.overview_surface = bool(snapshot and snapshot['metadata']['height']['mode'] == 'all'
                                            and snapshot['metadata']['below_y'] is None)
        self.canvas.update()
        active = self.world_mode.isChecked()
        self.world_map.set_snapshot(snapshot)
        self.world_mode.setVisible(snapshot is not None)
        self.world_mode.setChecked(snapshot is not None and active)
        self._world_toggled()

    def _world_toggled(self):
        self._update_layout()

    def _overview_images(self):
        self.canvas.overview = self.world_map.base.copy()
        self.canvas.overview_tiles = self.world_map.images.copy()
        self.canvas.update()

    def _overview_request(self):
        if self.collapsed or self.large and self.world_mode.isChecked():
            self.world_map.viewport = None
        else:
            area = self.canvas.layout.area("top")
            rect = self.canvas.tile_rect("top")
            self.world_map.viewport = ((area.left(), area.top()), (area.right(), area.bottom()),
                                       max(.001, rect.width() / max(.001, area.width())))
        self.world_map.request()

    def reposition(self):
        parent = self.parentWidget()
        available = max(1, parent.width() - self.right_inset)
        width = parent.width() if self.large else min(available, 288)
        height = parent.height() if self.large else MAP_HEADER_HEIGHT + (0 if self.collapsed else width)
        if not self.large and not self.collapsed and self.canvas.dimension:
            height += MAP_HEADER_HEIGHT
        if not self.large and not self.collapsed:
            height += MAP_HEADER_HEIGHT
        self.setFixedSize(width, height)
        self.move(0 if self.large else available - width, 0)
        self.raise_()
        self.canvas.view_changed.emit()

    def set_document(self, session):
        self.maps.reset()
        same_source = getattr(self, "source", None) == (session.path, getattr(session, "dimension", None))
        self.source = session.path, getattr(session, "dimension", None)
        if not same_source:
            self.cache.set_source(None)
        self.canvas.size_blocks = session.size
        self.canvas.origin = session.origin
        self.canvas.dimension = getattr(session, "dimension", None)
        self.canvas.overview_current = not session.dirty
        self.canvas.images.clear()
        self.canvas.image_pixels.clear()
        self.canvas.map_cut = None
        self.canvas.cave_y = None
        self.canvas.selection = None
        if not same_source:
            self.canvas.layout.reset()
        self.canvas.set_entities([])
        self._update_layout()
        self.show()

    def set_camera(self, position, direction):
        self.canvas.position, self.canvas.direction = tuple(position), tuple(direction)
        self.world_map.set_camera(tuple(p + o for p, o in zip(position, self.canvas.origin)), direction)
        self._overview_request()
        outside = any(p < 0 or p >= size for p, size in zip(position, self.canvas.size_blocks))
        text = "Outside · Load here" if outside else "Load here · F5"
        if self.load_here.text() != text:
            self.load_here.setText(text)
        self.load_here.setToolTip(("Camera is outside the loaded area. " if outside else "") +
                                 "Click or press F5 to load around the camera. Your edits stay. Hatched areas have no map data.")
        self.maps.update()
        self.canvas.update()

    def set_selection(self, bounds):
        self.canvas.selection = bounds
        self.canvas.update()

    def set_images(self, result):
        images, atlas, notice = result
        self.canvas.set_images(images)
        self.cache.set_source(atlas)
        if notice:
            self.header.setToolTip(notice)

    def recenter(self):
        if self.world_mode.isChecked():
            self.world_map.recenter()
            return
        self.canvas.layout.recenter()
        self.canvas.view_changed.emit()
        self.canvas.update()

    def _navigate(self, position):
        self.set_large(False)
        self.navigate.emit(position)

    def keyPressEvent(self, event):
        if not event.isAutoRepeat():
            if control_key(event) in (Qt.Key.Key_M, Qt.Key.Key_Escape):
                self.set_large(False)
            elif control_key(event) == Qt.Key.Key_F:
                self.recenter()
        event.accept()
