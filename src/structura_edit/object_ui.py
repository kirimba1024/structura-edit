from PySide6.QtCore import QObject, Qt
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QLabel, QToolButton

import pyvista as pv

from .appearance import ACCENT
from .object_inspector import ObjectInspector
from .object_search_ui import ObjectFinder
from .scene_lines import box_outlines


class ObjectController(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.keys = set()
        self.marker = None
        self.marked = None
        self.dialog = None
        self.finder = ObjectFinder(window)
        self.inspect_button = QToolButton()
        self.inspect_button.setText("Inspect…")
        self.inspect_button.clicked.connect(self.inspect)
        self.inspect_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        window.statusBar().addPermanentWidget(self.inspect_button)

    def reset(self):
        self.finder.reset()
        self.keys.clear()
        self.marked = None
        self.refresh()
        if self.dialog is not None:
            self.dialog.close()

    def select(self, key, extend=False):
        if not extend:
            self.keys = {key}
        elif key in self.keys:
            self.keys.remove(key)
        else:
            self.keys.add(key)
        self.refresh()
        self.window.status.setText(f"{len(self.keys)} entities selected · Inspect to view inventories and data")
        self.window._sync()

    def select_region(self):
        window = self.window
        if not self.available():
            return
        if window.selected.region is None:
            self._selected(window.session._entities)
            return
        window._run("objects", self._selected, session=window.session.fork(), operation="select", selection=window.selected.region)

    def _selected(self, keys):
        window = self.window
        self.keys = set(keys)
        self.refresh()
        window.status.setText(f"{len(self.keys)} entities selected in {'region' if window.selected.region else 'loaded area'}")
        window._sync()

    def available(self):
        window = self.window
        return (window.session is not None and not window.worker.busy and window.pending is None
                and not window.placement.active and not window.repeat.active)

    def sync(self):
        window = self.window
        single_block = window.selected.region is not None and window.selected.region.volume == 1
        ready = self.available()
        self.inspect_button.setVisible(window.session is not None)
        self.inspect_button.setEnabled(ready and (bool(self.keys) or single_block))
        actions = window.menus.actions
        actions["inspect"].setEnabled(self.inspect_button.isEnabled())
        actions["entity_all"].setEnabled(ready)
        for name in ("entity_move", "entity_duplicate", "entity_rotate", "entity_delete"):
            actions[name].setEnabled(ready and bool(self.keys) and not window.session.readonly)
        self.finder.sync()

    def refresh(self):
        session, scene = self.window.session, self.window.scene
        if session is not None:
            self.keys.intersection_update(session._entities)
        bounds = tuple(scene.entity_bounds[key] for key in sorted(self.keys) if key in scene.entity_bounds)
        if bounds == self.marked:
            return
        self.marked = bounds
        if self.marker is not None:
            scene.plotter.remove_actor(self.marker, reset_camera=False, render=False)
            self.marker = None
        if bounds:
            points, lines = box_outlines(bounds)
            mesh = pv.PolyData(points, lines=lines)
            self.marker = scene.plotter.add_mesh(mesh, color=ACCENT, line_width=2, lighting=False,
                                                 pickable=False, reset_camera=False, render=False)
            self.marker.SetUseBounds(False)
        scene.plotter.render()

    def inspect(self):
        if not self.available():
            return
        window = self.window
        position = window.selected.region.lower if not self.keys and window.selected.region is not None else None
        window.navigation.suspend()
        window._run("objects", self._inspected, session=window.session.fork(), operation="inspect", keys=tuple(sorted(self.keys)), position=position)

    def _inspected(self, records):
        if not records:
            return
        if self.dialog is not None:
            self.dialog.close()
        self.dialog = ObjectInspector(self.window, records, readonly=self.window.session.readonly)
        dialog = self.dialog
        revision = self.window.session.revision
        self.dialog.requested.connect(lambda edits: self._edit(revision, edits))
        self.dialog.finished.connect(lambda result: self._closed(dialog))
        self.dialog.show()
        self.dialog.activateWindow()

    def _closed(self, dialog):
        if self.dialog is dialog:
            self.dialog = None
            if QApplication.applicationState() == Qt.ApplicationState.ApplicationActive:
                self.window.activateWindow()
            target = self.finder.panel.search if self.finder.panel.isVisible() else self.window.plotter
            target.setFocus()

    def _edit(self, revision, edits):
        if not self.available() or revision != self.window.session.revision:
            if self.dialog is not None:
                self.dialog.errors.setText("Document changed; reopen the inspector")
            return
        self.window._run("objects", self._prepared, session=self.window.session.fork(), operation="edit", edits=edits)

    def transform(self, action):
        if not self.available() or not self.keys:
            return
        window = self.window
        window.navigation.suspend()
        dialog = QDialog(window)
        dialog.setWindowTitle(f"{action} {len(self.keys)} entities")
        form = QFormLayout(dialog)
        fields = []
        for label in (("Angle around Y",) if action == "Rotate" else ("Offset X", "Offset Y (up / down)", "Offset Z") if action != "Delete" else ()):
            value = QDoubleSpinBox()
            value.setDecimals(2)
            value.setRange(-30_000_000, 30_000_000)
            value.setValue(90 if action == "Rotate" else 0)
            form.addRow(label, value)
            fields.append(value)
        if action == "Delete":
            form.addRow(QLabel("Remove selected entities from this document. Undo remains available."))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if not dialog.exec():
            window.plotter.setFocus()
            return
        values = dict(angle=fields[0].value()) if action == "Rotate" else dict(offset=tuple(field.value() for field in fields)) if fields else {}
        window._run("objects", self._prepared, session=window.session.fork(), operation="transform", keys=tuple(sorted(self.keys)), action=action, **values)

    def _prepared(self, change):
        if not change:
            self.window.status.setText("No changes")
            return
        selected = {delta.key for delta in change.entities if delta.after is not None}
        self.window._run("apply", lambda session: self._applied(session, selected), session=self.window.session, change=change)

    def _applied(self, session, selected):
        window = self.window
        window._resized_document(session)
        window.session = session
        if self.dialog is not None:
            self.dialog.close()
        self.keys = selected & session._entities.keys()
        window._refresh_palette()
        window.render_scene()
        window.plotter.setFocus()
        window.status.setText("Object changes applied · Undo is available")
        window._sync()
