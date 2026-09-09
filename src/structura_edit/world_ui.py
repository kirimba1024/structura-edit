from copy import copy

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QLabel, QSpinBox,
)

from .world_view import WorldView
from .loading import DEFAULT_RADIUS, DEFAULT_VERTICAL_RADIUS, check_world_budget
from .height_slice import HeightSlice


class WorldController(QObject):
    message = Signal(str)
    opening = Signal()
    open_requested = Signal()

    def __init__(self, document, tasks, camera, selection, *, options, available, opened):
        super().__init__()
        self.document, self.tasks, self.camera = document, tasks, camera
        self.plotter, self.selection = camera.plotter, selection
        self.options, self.available, self.opened = options, available, opened
        self.path = None
        self.dimension = None
        self.center = None
        self.radius = DEFAULT_RADIUS
        self.vertical_radius = DEFAULT_VERTICAL_RADIUS
        self.queued = None
        self.generation = 0

    @property
    def active(self):
        return isinstance(self.document.session, WorldView)

    def open(self, path):
        if self.tasks.busy:
            return
        self.path, self.dimension, self.center = str(path), None, None
        self.request(preserve_edits=False)

    def reset_request(self):
        self.generation += 1
        self.queued = None
        session = self.document.session
        if self.active:
            self.path = str(session.path)
            self.dimension, self.center = session.dimension, session.center
            self.radius, self.vertical_radius = session.radius, session.vertical_radius
        else:
            self.path = self.dimension = self.center = None

    def camera_position(self):
        return tuple(p + o for p, o in zip(self.plotter.camera.position, self.document.session.origin))

    def refresh(self):
        if self.active and self.available() and self.document.pending is None:
            self.center = self.camera_position()
            self.request()

    def request(self, *, recenter=False, preserve_edits=True):
        if not self.path:
            return
        if self.center is not None:
            try:
                check_world_budget(self.center, self.radius, self.vertical_radius)
            except ValueError as error:
                self.message.emit(str(error))
                self.reset_request()
                return
        self.generation += 1
        args = dict(path=self.path, center=self.center, dimension=self.dimension, radius=self.radius,
                    vertical_radius=self.vertical_radius, recenter=recenter, generation=self.generation,
                    **self.options(),
                    preserve_edits=preserve_edits)
        preserve_view = (preserve_edits and not recenter and self.active and str(self.document.session.path) == self.path
                         and self.document.session.dimension == self.dimension)
        if not preserve_view:
            args["height"] = HeightSlice()
        if self.tasks.busy:
            self.queued = args
            self.message.emit("World refresh queued")
            return
        self.queued = None
        self._submit(args)

    def _submit(self, args):
        session = self.document.session
        if args["preserve_edits"] and self.active and str(session.path) == args["path"]:
            args = dict(args, world_changes=session.world_changes)
        def received(result):
            if (self.generation == args["generation"] and self.path == args["path"]
                    and self.options()["include_entities"] == args["include_entities"]):
                self.received(result, recenter=args["recenter"])
        self.tasks.submit("world", received, **args)

    def received(self, result, *, recenter=False):
        plotter = self.plotter
        suppressed = plotter.suppress_rendering
        plotter.suppress_rendering = True
        try:
            self._replace_view(result, recenter=recenter)
        finally:
            plotter.suppress_rendering = suppressed
            plotter.render()

    def _replace_view(self, result, *, recenter=False):
        session, rendered = result
        previous = self.document.session
        preserve = not recenter and self.active and (previous.path, previous.dimension) == (session.path, session.dimension)
        camera = self.camera_position() if preserve else None
        direction = self.plotter.camera.direction
        selection = copy(self.document.selected)
        self.opened(session, rendered=rendered, fit=False, preserve_focus=preserve)
        self.path, self.dimension, self.center = str(session.path), session.dimension, session.center
        local = tuple(p - o for p, o in zip(camera or session.center, session.origin))
        if preserve:
            self.plotter.camera.position = local
            self.plotter.camera.focal_point = tuple(p + d for p, d in zip(local, direction))
        else:
            self.plotter.camera.position = tuple(p + d for p, d in zip(local, (12, 10, 12)))
            self.plotter.camera.focal_point = local
        self.plotter.camera.up = (0, 1, 0)
        if preserve and selection.region is not None:
            offset = tuple(old - new for old, new in zip(previous.origin, session.origin))
            try:
                region = selection.region.shifted(offset)
                self.document.selected.set_bounds(region.lower, region.upper)
                if selection.anchor is not None:
                    self.document.selected.anchor = tuple(p + d for p, d in zip(selection.anchor, offset))
                self.document.selected.set_extending(selection.extending)
            except ValueError:
                self.document.selected.clear()
            self.selection.changed.emit()
        self.camera.needs_render = True
        self.camera.render()
        self.message.emit(f"{session.world_name} · {session.dimension} · {len(session.loaded_chunks)} chunks · "
                              f"{len(session.missing_chunks)} absent · {len(session._document.source.entities)} entities · Refresh: F5")

    def flush(self):
        if self.queued and not self.tasks.busy:
            args, self.queued = self.queued, None
            self._submit(args)

    def settings(self):
        if not self.active:
            self.open_requested.emit()
            return
        self.opening.emit()
        dialog = WorldSettings(self.plotter.window(), self.document.session, self.camera_position(),
                               self.dimension, self.radius, self.vertical_radius)
        if dialog.exec():
            self.dimension = dialog.dimension.currentText()
            self.center = tuple(field.value() for field in dialog.coordinates)
            self.radius, self.vertical_radius = dialog.radius.value(), dialog.vertical.value()
            self.request(recenter=True)


class WorldSettings(QDialog):
    def __init__(self, parent, session, center, dimension, radius, vertical):
        super().__init__(parent)
        self.setWindowTitle("World view")
        layout = QFormLayout(self)
        layout.addRow(QLabel(str(session.path)))
        self.dimension = QComboBox()
        self.dimension.addItems(session.dimensions)
        self.dimension.setCurrentText(dimension)
        layout.addRow("Dimension", self.dimension)
        self.coordinates = []
        for axis, value in zip("XYZ", center):
            field = QSpinBox(minimum=-30_000_000, maximum=30_000_000, value=round(value))
            self.coordinates.append(field)
            layout.addRow("Center " + axis, field)
        self.radius, self.vertical = QSpinBox(), QSpinBox()
        self.radius.setRange(0, 4)
        self.radius.setValue(radius)
        self.radius.setToolTip("Square of (2 × radius + 1) chunks; one chunk is 16 × 16 blocks")
        self.vertical.setRange(16, 192)
        self.vertical.setSingleStep(16)
        self.vertical.setValue(vertical)
        layout.addRow("Radius · chunks", self.radius)
        layout.addRow("Vertical radius · blocks", self.vertical)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.RestoreDefaults)
        layout.addRow(buttons)
        def reset():
            self.radius.setValue(DEFAULT_RADIUS)
            self.vertical.setValue(DEFAULT_VERTICAL_RADIUS)
            self.dimension.setCurrentText(session.dimension)
            for field, value in zip(self.coordinates, center):
                field.setValue(round(value))
        buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(reset)
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.accept)
        buttons.rejected.connect(self.reject)
