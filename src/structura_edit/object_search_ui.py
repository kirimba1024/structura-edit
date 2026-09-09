from PySide6.QtCore import QObject, QTimer, Qt, Signal

from .object_search import PAGE_SIZE, search_revision
from .object_search_panel import ObjectSearchPanel


class ObjectFinder(QObject):
    opening = Signal()
    requested = Signal(str, object)

    def __init__(self, plotter, document, tasks, *, available):
        super().__init__(plotter)
        self.document, self.tasks, self.available = document, tasks, available
        self.plotter = plotter
        self.panel = ObjectSearchPanel(plotter)
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
        if not self.available():
            return
        self.opening.emit()
        self.panel.show()
        self.panel.reposition()
        self.panel.search.setFocus(Qt.FocusReason.OtherFocusReason)
        self.changed()

    def close(self):
        self.panel.hide()
        self.timer.stop()
        self.plotter.setFocus(Qt.FocusReason.OtherFocusReason)

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
        self.panel.model.replace((), self.document.session.origin if self.document.session else (0, 0, 0))
        self.panel.info.setText("Searching…")
        self.describe()
        if self.panel.isVisible():
            self.timer.start(200)

    def page(self, step):
        self.offset = max(0, self.offset + step * PAGE_SIZE)
        self.queue()

    def sync(self, *, hidden=False, bottom=0):
        panel = self.panel
        if hidden:
            panel.hide()
            self.timer.stop()
        panel.in_selection.setEnabled(self.document.selected.region is not None)
        revision = (search_revision(self.document.session), self.document.selected.current if panel.in_selection.isChecked() else None) if self.document.session else None
        if revision != self.revision:
            self.revision = revision
            self.changed()
        if self.inflight is not None and self.tasks.kind != "object_search":
            self.inflight = None
            if not self.pending:
                panel.info.setText("Search stopped · Enter to retry")
        if self.pending and panel.isVisible() and not self.timer.isActive() and self.available():
            self.timer.start(200)
        panel.reposition(bottom)
        self.describe()

    def submit(self):
        panel = self.panel
        if not panel.isVisible() or not self.pending or not self.available():
            return
        if panel.in_selection.isChecked() and self.document.selected.current is None:
            self.pending = False
            panel.info.setText("Select a region first")
            return
        token = self.generation, self.revision
        self.pending = False
        self.inflight = token
        self.tasks.submit("object_search", lambda result: self.received(token, result), session=self.document.session.fork(),
                    query=dict(text=panel.search.text(), kind=panel.kind.currentData(),
                               selection=self.document.selected.current if panel.in_selection.isChecked() else None, offset=self.offset))

    def received(self, token, result):
        self.inflight = None
        if token != (self.generation, self.revision):
            return
        self.shown, self.result = token, result
        self.panel.model.replace(result.rows, self.document.session.origin)
        if result.rows:
            self.panel.results.setCurrentIndex(self.panel.model.index(0, 0))
        count = f"{result.offset + 1:,}–{result.offset + len(result.rows):,} / {result.total:,}" if result.rows else "No matches"
        self.panel.info.setText(count)
        self.panel.info.setToolTip(f"{result.total:,} matches in {'selected region' if self.panel.in_selection.isChecked() else 'loaded area'}; empty space is excluded")
        self.describe()

    def describe(self, *args):
        panel = self.panel
        rows = panel.selected()
        ready = self.shown == (self.generation, self.revision) and self.available()
        compatible = bool(rows) and (len(rows) == 1 or all(row.kind == "entity" for row in rows))
        for action in panel.actions.values():
            action.setEnabled(ready and compatible)
            action.setToolTip("Choose one block or one or more entities on this page")
        panel.previous.setEnabled(ready and self.result is not None and self.offset > 0)
        panel.next.setEnabled(ready and self.result is not None and self.offset + PAGE_SIZE < self.result.total)
        if len(rows) == 1:
            row = rows[0]
            panel.identity.setText(row.identity)
            panel.position.setText(" · ".join(f"{axis} {value + origin:g}" for axis, value, origin in zip("XYZ", row.position, self.document.session.origin)))
        else:
            panel.identity.setText(f"{len(rows)} objects" if rows else "Choose an object")
            panel.position.setText("Select one block or several entities" if rows and not compatible else "")

    def act(self, action):
        if not self.panel.actions[action].isEnabled():
            return
        if search_revision(self.document.session) != self.revision[0]:
            self.sync()
            return
        self.requested.emit(action, self.panel.selected())
        if action != "inspect":
            self.panel.search.setFocus(Qt.FocusReason.OtherFocusReason)
