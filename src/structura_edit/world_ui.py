from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QLabel, QSpinBox,
)

from .world_view import WorldView
from .loading import DEFAULT_RADIUS, DEFAULT_VERTICAL_RADIUS, check_world_budget


class WorldController:
    def __init__(self, window):
        self.window = window
        self.path = None
        self.dimension = None
        self.center = None
        self.radius = DEFAULT_RADIUS
        self.vertical_radius = DEFAULT_VERTICAL_RADIUS
        self.queued = None
        self.generation = 0

    @property
    def active(self):
        return isinstance(self.window.session, WorldView)

    def open_dialog(self):
        path = QFileDialog.getExistingDirectory(self.window, "Open Java world · folder containing level.dat")
        if path:
            self.open(path)

    def open(self, path):
        if self.window.worker.busy or not self.window._confirm_discard():
            return
        self.path, self.dimension, self.center = str(path), None, None
        self.request()

    def camera_position(self):
        return tuple(p + o for p, o in zip(self.window.plotter.camera.position, self.window.session.origin))

    def refresh(self):
        if self.active:
            self.center = self.camera_position()
            self.request()

    def request(self, *, recenter=False):
        if not self.path:
            return
        if self.center is not None:
            try:
                check_world_budget(self.center, self.radius, self.vertical_radius)
            except ValueError as error:
                self.window.status.setText(str(error))
                return
        self.generation += 1
        args = dict(path=self.path, center=self.center, dimension=self.dimension, radius=self.radius,
                    vertical_radius=self.vertical_radius, assets=self.window.assets,
                    include_entities=self.window.entities_action.isChecked(), recenter=recenter, generation=self.generation)
        if self.window.worker.busy:
            self.queued = args
            self.window.status.setText("World refresh queued")
            return
        self.queued = None
        self._submit(args)

    def _submit(self, args):
        def received(result):
            if (self.generation == args["generation"] and self.path == args["path"]
                    and self.window.entities_action.isChecked() == args["include_entities"]):
                self.received(result, recenter=args["recenter"])
        self.window._run("world", received, **args)

    def received(self, result, *, recenter=False):
        plotter = self.window.plotter
        suppressed = plotter.suppress_rendering
        plotter.suppress_rendering = True
        try:
            self._replace_view(result, recenter=recenter)
        finally:
            plotter.suppress_rendering = suppressed
            plotter.render()

    def _replace_view(self, result, *, recenter=False):
        session, rendered = result
        window = self.window
        preserve = not recenter and self.active and window.session.path == session.path and window.session.dimension == session.dimension
        camera = self.camera_position() if preserve else None
        direction = window.plotter.camera.direction
        old_selection = None
        old_anchor = None
        extending = window.selected.extending
        if preserve and window.selected.region is not None:
            old_selection = tuple(tuple(p + o for p, o in zip(bound, window.session.origin))
                                  for bound in (window.selection().lower, window.selection().upper))
            if window.selected.anchor is not None:
                old_anchor = tuple(p + o for p, o in zip(window.selected.anchor, window.session.origin))
        window._opened(session, rendered=rendered, fit=False, preserve_focus=preserve)
        self.path, self.dimension, self.center = str(session.path), session.dimension, session.center
        local = tuple(p - o for p, o in zip(camera or session.center, session.origin))
        if preserve:
            window.plotter.camera.position = local
            window.plotter.camera.focal_point = tuple(p + d for p, d in zip(local, direction))
        else:
            window.plotter.camera.position = tuple(p + d for p, d in zip(local, (12, 10, 12)))
            window.plotter.camera.focal_point = local
        window.plotter.camera.up = (0, 1, 0)
        if old_selection:
            bounds = tuple(tuple(p - o for p, o in zip(bound, session.origin)) for bound in old_selection)
            try:
                session.select(bounds)
                window.set_selection_bounds(*bounds)
                if old_anchor is not None:
                    window.selected.anchor = tuple(p - o for p, o in zip(old_anchor, session.origin))
                window.selected.set_extending(extending)
            except ValueError:
                window.clear_selection()
        window.camera.needs_render = True
        window.camera.render()
        window.status.setText(f"{session.world_name} · {session.dimension} · {len(session.loaded_chunks)} chunks · "
                              f"{len(session.missing_chunks)} absent · {len(session._document.source.entities)} entities · Refresh: F5")

    def flush(self):
        if self.queued and not self.window.worker.busy:
            args, self.queued = self.queued, None
            self._submit(args)

    def settings(self):
        if not self.active:
            self.open_dialog()
            return
        window = self.window
        window.navigation.stop()
        dialog = QDialog(window)
        dialog.setWindowTitle("World view")
        layout = QFormLayout(dialog)
        layout.addRow(QLabel(str(self.path)))
        dimension = QComboBox()
        dimension.addItems(window.session.dimensions)
        dimension.setCurrentText(self.dimension)
        layout.addRow("Dimension", dimension)
        coordinates = []
        for axis, value in zip("XYZ", self.camera_position()):
            field = QSpinBox()
            field.setRange(-30_000_000, 30_000_000)
            field.setValue(round(value))
            coordinates.append(field)
            layout.addRow("Center " + axis, field)
        radius, vertical = QSpinBox(), QSpinBox()
        radius.setRange(0, 4)
        radius.setValue(self.radius)
        radius.setToolTip("Square of (2 × radius + 1) chunks; one chunk is 16 × 16 blocks")
        vertical.setRange(16, 192)
        vertical.setSingleStep(16)
        vertical.setValue(self.vertical_radius)
        layout.addRow("Radius · chunks", radius)
        layout.addRow("Vertical radius · blocks", vertical)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.RestoreDefaults)
        layout.addRow(buttons)
        def reset():
            radius.setValue(DEFAULT_RADIUS)
            vertical.setValue(DEFAULT_VERTICAL_RADIUS)
            dimension.setCurrentText(window.session.dimension)
            for field, value in zip(coordinates, self.camera_position()):
                field.setValue(round(value))
        def apply():
            self.radius, self.vertical_radius = radius.value(), vertical.value()
            self.dimension = dimension.currentText()
            self.center = tuple(field.value() for field in coordinates)
            dialog.accept()
            self.request(recenter=True)
        buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(reset)
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(apply)
        buttons.rejected.connect(dialog.reject)
        dialog.exec()
