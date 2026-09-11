from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QLabel

import pyvista as pv

from .appearance import SELECTION, SELECTION_WIDTH
from .object_labels import selected_labels
from .item_icons import ItemIcons
from .object_inspector import ObjectInspector
from .object_search_ui import ObjectFinder
from .scene_lines import box_outlines


class ObjectController(QObject):
    changed = Signal()
    message = Signal(str)
    applied = Signal()
    reveal_requested = Signal(object)

    def __init__(self, document, tasks, edits, scene, navigation, selection, *, available, assets=lambda: None, labels=lambda values: None):
        super().__init__(navigation)
        self.document, self.tasks, self.edits = document, tasks, edits
        self.scene, self.navigation, self.selection = scene, navigation, selection
        self.available = available
        self.labels = labels
        self.icons = ItemIcons(tasks.submit, assets)
        self.keys = set()
        self.marker = None
        self.marked = None
        self.dialog = None
        self.region_dialog = None
        self.pending_edit = None
        self.edit_timer = QTimer(self)
        self.edit_timer.setInterval(25)
        self.edit_timer.timeout.connect(self._flush_edit)
        self.finder = ObjectFinder(scene.plotter, document, tasks, available=available)
        self.finder.requested.connect(self._found)

    def reset(self):
        self.finder.reset()
        self.keys.clear()
        self.marked = None
        self.refresh()
        if self.dialog is not None:
            self.dialog.close()
        if self.region_dialog is not None:
            self.region_dialog.close()

    def select(self, key, extend=False):
        if not extend:
            self.keys = {key}
        elif key in self.keys:
            self.keys.remove(key)
        else:
            self.keys.add(key)
        self.refresh()
        self.message.emit(f"{len(self.keys)} entities selected · Inspect to view inventories and data")
        self.changed.emit()

    def select_region(self):
        if not self.available():
            return
        if self.document.selected.current is None:
            self._selected(self.document.session._entities)
            return
        self._submit("select", self._selected, selection=self.document.selected.current)

    def _selected(self, keys):
        self.keys = set(keys)
        self.refresh()
        self.message.emit(f"{len(self.keys)} entities selected in {'region' if self.document.selected.current else 'loaded area'}")
        self.changed.emit()

    def refresh(self):
        session, scene = self.document.session, self.scene
        if session is not None:
            self.keys.intersection_update(session._entities)
        self.labels(selected_labels(session, self.keys, scene.entity_bounds) if session is not None else ())
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
            self.marker = scene.plotter.add_mesh(mesh, color=SELECTION, line_width=SELECTION_WIDTH, lighting=False,
                                                 pickable=False, reset_camera=False, render=False)
            self.marker.SetUseBounds(False)
        scene.plotter.render()

    def inspect(self):
        if not self.available():
            return
        selection = self.document.selected.current
        if not self.keys and selection is not None and selection.volume > 1:
            from .region_inspector import RegionInspector

            if self.region_dialog is not None:
                self.region_dialog.close()
            self.navigation.suspend()
            self.region_dialog = RegionInspector(self.scene.plotter.window(), self.document.session, selection)
            token = self.document.session_token
            def open_object(kind, key):
                if self.available() and token == self.document.session_token:
                    self._submit('inspect', self._inspected, keys=(key,) if kind == 'entity' else (),
                                 position=key if kind == 'data' else None)
            self.region_dialog.object_requested.connect(open_object)
            self.region_dialog.finished.connect(lambda _: setattr(self, 'region_dialog', None))
            self.region_dialog.show()
            return
        position = self.document.selected.current.lower if not self.keys and self.document.selected.current is not None else None
        self.navigation.suspend()
        self._submit("inspect", self._inspected, keys=tuple(sorted(self.keys)), position=position)

    def _inspected(self, records):
        if not records:
            return
        if self.dialog is not None:
            self.dialog.close()
        self.dialog = ObjectInspector(self.scene.plotter.window(), records, readonly=self.document.session.readonly,
                                      icons=self.icons)
        dialog = self.dialog
        token = self.document.session_token
        self.dialog.requested.connect(lambda edits: self._edit(token, edits))
        self.dialog.finished.connect(lambda result: self._closed(dialog))
        self.dialog.show()
        self.dialog.activateWindow()

    def _closed(self, dialog):
        if self.dialog is dialog:
            self.pending_edit = None
            self.edit_timer.stop()
            self.dialog = None
            if QApplication.applicationState() == Qt.ApplicationState.ApplicationActive:
                self.scene.plotter.window().activateWindow()
            target = self.finder.panel.search if self.finder.panel.isVisible() else self.scene.plotter
            target.setFocus()

    def _edit(self, token, edits):
        if token != self.document.session_token:
            if self.dialog is not None:
                self.dialog.errors.setText("Document changed; reopen the inspector")
            return
        if self.tasks.busy:
            if self.dialog is not None:
                self.pending_edit = token, edits
                self.dialog.apply.setEnabled(False)
                self.dialog.tabs.setEnabled(False)
                self.dialog.errors.setText("Waiting for the current task before applying…")
                self.edit_timer.start()
            return
        if not self.available():
            if self.dialog is not None:
                self.dialog.errors.setText("Finish the current operation before applying these changes")
            return
        self._submit("edit", self._prepared, edits=edits)

    def _flush_edit(self):
        if self.tasks.busy:
            return
        self.edit_timer.stop()
        pending, self.pending_edit = self.pending_edit, None
        if self.dialog is not None and pending is not None:
            self.dialog.apply.setEnabled(True)
            self.dialog.tabs.setEnabled(True)
            self._edit(*pending)

    def transform(self, action):
        if not self.available() or not self.keys:
            return
        self.navigation.suspend()
        dialog = QDialog(self.scene.plotter.window())
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
            self.scene.plotter.setFocus()
            return
        values = dict(angle=fields[0].value()) if action == "Rotate" else dict(offset=tuple(field.value() for field in fields)) if fields else {}
        self._submit("transform", self._prepared, keys=tuple(sorted(self.keys)), action=action, **values)

    def _submit(self, operation, callback, **args):
        token = self.document.session_token
        def received(result):
            if token == self.document.session_token:
                callback(result)
        return self.tasks.submit("objects", received, session=self.document.session.fork(), operation=operation, **args)

    def _found(self, action, rows):
        if rows[0].kind == "block":
            self.keys.clear()
            self.refresh()
            position = rows[0].position
            self.selection.set_bounds(position, tuple(v + 1 for v in position))
        else:
            self._selected(row.key for row in rows)
        if action == "inspect":
            self.inspect()
        elif action == "show":
            bounds = [self.scene.entity_bounds.get(row.key, (row.position, tuple(v + 1 for v in row.position))) for row in rows]
            self.navigation.camera.focus_bounds(bounds)
            self.reveal_requested.emit(tuple(row.position for row in rows))

    def _prepared(self, change):
        if not change:
            self.message.emit("No changes")
            return
        selected = {delta.key for delta in change.entities if delta.after is not None}
        self.edits.commit(change, lambda session: self._applied(session, selected))

    def _applied(self, session, selected):
        if self.dialog is not None:
            self.dialog.close()
        self.keys = selected & session._entities.keys()
        self.applied.emit()
        self.scene.plotter.setFocus()
        self.message.emit("Object changes applied · Undo is available")
        self.changed.emit()
