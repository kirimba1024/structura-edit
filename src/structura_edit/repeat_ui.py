from PySide6.QtCore import QObject, Signal

from .repeat_bar import RepeatBar


class RepeatController(QObject):
    changed = Signal()
    started = Signal()
    apply_requested = Signal()
    cancel_requested = Signal()

    def __init__(self, view, document, edits, tasks):
        super().__init__(view)
        self.view, self.document, self.edits, self.tasks = view, document, edits, tasks
        self.bar = RepeatBar(view)
        self.source = None
        self.placing = False
        self.bar.changed.connect(self.invalidate)
        self.bar.preview_requested.connect(self.preview)
        self.bar.apply_requested.connect(self.apply_requested)
        self.bar.cancel_requested.connect(self.close)

    @property
    def active(self):
        return self.source is not None and self.source == self.document.selection_token

    @property
    def plan(self):
        preview = self.document.preview
        return preview.plan if preview is not None and preview.kind == "repeat" else None

    def start(self):
        session = self.document.session
        if (session is None or session.readonly or self.tasks.busy or self.placing
                or self.document.selected.current is None or self.document.pending is not None):
            return
        self.source = self.document.selection_token
        self.started.emit()
        self.changed.emit()

    def preview(self):
        if self.active:
            self.edits.prepare("repeat", **self.bar.values(self.document.selection()))

    def invalidate(self):
        self.edits.invalidate()
        self.changed.emit()

    def close(self):
        if self.tasks.protected:
            return
        self.source = None
        if self.tasks.busy:
            self.cancel_requested.emit()
        else:
            self.edits.invalidate()
        self.bar.hide()
        self.view.setFocus()
        self.changed.emit()

    def sync(self, *, placing, large, scene_ready):
        self.placing = placing
        self.bar.setVisible(self.active and not large)
        if not self.active:
            return
        ready = self.document.session is not None and not self.tasks.busy
        for field in self.bar.inputs:
            field.setEnabled(ready)
        blocks = self.bar.content.blocks.isChecked()
        self.bar.air.setEnabled(ready and blocks)
        self.bar.destination.setEnabled(ready and blocks)
        self.bar.preview.setEnabled(ready and (blocks or self.bar.content.entities.isChecked()))
        self.bar.apply.setEnabled(ready and bool(self.document.pending) and scene_ready)
        self.bar.cancel.setEnabled(not self.tasks.protected)
        self.bar.info.setText(self.plan.summary + " · one Undo" if self.plan is not None else "Repeat selection · original stays")
        self.bar.reposition()
