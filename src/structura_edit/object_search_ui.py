from math import sqrt

from PySide6.QtCore import QObject, QTimer, Qt

from .object_search import PAGE_SIZE, search_revision
from .object_search_panel import ObjectSearchPanel


class ObjectFinder(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.panel = ObjectSearchPanel(window.plotter)
        self.panel.changed.connect(self.changed)
        self.panel.requested.connect(self.act)
        self.panel.page_requested.connect(self.page)
        self.panel.dismissed.connect(self.close)
        self.panel.results.selectionModel().selectionChanged.connect(self.describe)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.submit)
        self.generation = self.offset = 0
        self.pending = False
        self.inflight = self.revision = self.shown = self.result = None

    def show(self):
        if not self.window.objects.available():
            return
        self.window.navigation.stop()
        self.window.minimap.set_large(False)
        self.window.panels.dismiss()
        self.panel.show()
        self.panel.reposition()
        self.panel.search.setFocus(Qt.FocusReason.OtherFocusReason)
        self.changed()

    def close(self):
        self.panel.hide()
        self.timer.stop()
        self.window.plotter.setFocus(Qt.FocusReason.OtherFocusReason)

    def reset(self):
        self.panel.hide()
        self.timer.stop()
        self.revision = None
        self.changed()

    def changed(self):
        self.offset = 0
        self.queue()

    def queue(self):
        self.generation += 1
        self.pending = True
        self.result = self.shown = None
        self.panel.model.replace((), self.window.session.origin if self.window.session else (0, 0, 0))
        self.panel.info.setText("Searching…")
        self.describe()
        if self.panel.isVisible():
            self.timer.start(200)

    def page(self, step):
        self.offset = max(0, self.offset + step * PAGE_SIZE)
        self.queue()

    def sync(self):
        window, panel = self.window, self.panel
        if window.minimap.large or window.placement.active or window.repeat.active:
            panel.hide()
            self.timer.stop()
        window.menus.actions["find_objects"].setEnabled(window.objects.available())
        panel.in_selection.setEnabled(window.selected.region is not None)
        revision = (search_revision(window.session), window.selected.region if panel.in_selection.isChecked() else None) if window.session else None
        if revision != self.revision:
            self.revision = revision
            self.changed()
        if self.inflight is not None and (window._job is None or window._job[0] != "object_search"):
            self.inflight = None
            if not self.pending:
                panel.info.setText("Search stopped · Enter to retry")
        if self.pending and panel.isVisible() and not self.timer.isActive() and window.objects.available():
            self.timer.start(200)
        bottom = window.placement.bar.height() if window.placement.bar.isVisible() else 0
        panel.reposition(bottom)
        self.describe()

    def submit(self):
        window, panel = self.window, self.panel
        if not panel.isVisible() or not self.pending or not window.objects.available():
            return
        if panel.in_selection.isChecked() and window.selected.region is None:
            self.pending = False
            panel.info.setText("Select a region first")
            return
        token = self.generation, self.revision
        self.pending = False
        self.inflight = token
        window._run("object_search", lambda result: self.received(token, result), session=window.session.fork(),
                    query=dict(text=panel.search.text(), kind=panel.kind.currentData(),
                               selection=window.selected.region if panel.in_selection.isChecked() else None, offset=self.offset))

    def received(self, token, result):
        self.inflight = None
        if token != (self.generation, self.revision):
            return
        self.shown, self.result = token, result
        self.panel.model.replace(result.rows, self.window.session.origin)
        if result.rows:
            self.panel.results.setCurrentIndex(self.panel.model.index(0, 0))
        count = f"{result.offset + 1:,}–{result.offset + len(result.rows):,} / {result.total:,}" if result.rows else "No matches"
        self.panel.info.setText(count)
        self.panel.info.setToolTip(f"{result.total:,} matches in {'selected region' if self.panel.in_selection.isChecked() else 'loaded area'}; empty space is excluded")
        self.describe()

    def describe(self, *args):
        panel, window = self.panel, self.window
        rows = panel.selected()
        ready = self.shown == (self.generation, self.revision) and window.objects.available()
        compatible = bool(rows) and (len(rows) == 1 or all(row.kind == "entity" for row in rows))
        for action in panel.actions.values():
            action.setEnabled(ready and compatible)
            action.setToolTip("Choose one block or one or more entities on this page")
        panel.previous.setEnabled(ready and self.result is not None and self.offset > 0)
        panel.next.setEnabled(ready and self.result is not None and self.offset + PAGE_SIZE < self.result.total)
        if len(rows) == 1:
            row = rows[0]
            panel.identity.setText(row.identity)
            panel.position.setText(" · ".join(f"{axis} {value + origin:g}" for axis, value, origin in zip("XYZ", row.position, window.session.origin)))
        else:
            panel.identity.setText(f"{len(rows)} objects" if rows else "Choose an object")
            panel.position.setText("Select one block or several entities" if rows and not compatible else "")

    def act(self, action):
        if not self.panel.actions[action].isEnabled():
            return
        window, rows = self.window, self.panel.selected()
        if search_revision(window.session) != self.revision[0]:
            self.sync()
            return
        if rows[0].kind == "block":
            window.objects.keys.clear()
            window.objects.refresh()
            position = rows[0].position
            window.selection_actions.set_bounds(position, tuple(v + 1 for v in position))
        else:
            window.objects._selected(row.key for row in rows)
        if action == "inspect":
            window.objects.inspect()
        elif action == "show":
            bounds = [window.scene.entity_bounds.get(row.key, (row.position, tuple(v + 1 for v in row.position))) for row in rows]
            lower = tuple(min(bound[0][axis] for bound in bounds) for axis in range(3))
            upper = tuple(max(bound[1][axis] for bound in bounds) for axis in range(3))
            center = tuple((lo + hi) / 2 for lo, hi in zip(lower, upper))
            distance = max(6, sqrt(sum((hi - lo) ** 2 for lo, hi in zip(lower, upper))) * 1.5)
            camera = window.plotter.camera
            camera.position = tuple(value - direction * distance for value, direction in zip(center, camera.direction))
            camera.focal_point = center
            window.camera.needs_render = True
            window.camera.render()
            low, high = window.slicing.value.interval(window.session)
            if any(not low <= row.position[1] < high for row in rows):
                window.slicing.mode.setCurrentIndex(0)
        if action != "inspect":
            self.panel.search.setFocus(Qt.FocusReason.OtherFocusReason)
