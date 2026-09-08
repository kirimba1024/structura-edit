from PySide6.QtCore import QObject

from .repeat_bar import RepeatBar


class RepeatController(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.bar = RepeatBar(window.plotter)
        self.active = False
        self.source = None
        self.plan = None
        self.bar.changed.connect(window._invalidate)
        self.bar.preview_requested.connect(self.preview)
        self.bar.apply_requested.connect(window.apply_pending)
        self.bar.cancel_requested.connect(self.close)

    def identity(self):
        window = self.window
        return (window.session._id, window.session.revision, window.selected.region) if window.session else None

    def start(self):
        window = self.window
        if (window.session is None or window.session.readonly or window.worker.busy or window.placement.active
                or window.selected.region is None or window.pending is not None):
            return
        window.navigation.stop()
        window.panels.dismiss()
        self.source = self.identity()
        self.active = True
        window._sync()

    def preview(self):
        if self.active:
            self.window._prepare_change("repeat", **self.bar.values(self.window.selection()))

    def close(self):
        window = self.window
        if window._job and window._job[0] in ("apply", "save", "export", "history"):
            return
        self.active = False
        if window.worker.busy:
            window.cancel_task()
        else:
            window._invalidate()
        self.bar.hide()
        window.plotter.setFocus()

    def sync(self):
        window = self.window
        if self.source != self.identity():
            self.active = False
        self.bar.setVisible(self.active and not window.minimap.large)
        ready = window.session is not None and not window.worker.busy
        window.menus.actions["repeat"].setEnabled(bool(ready and not window.session.readonly and window.selected.region
                                                       and not window.placement.active and window.pending is None and not self.active))
        if not self.active:
            return
        for field in self.bar.inputs:
            field.setEnabled(ready)
        blocks = self.bar.content.blocks.isChecked()
        self.bar.air.setEnabled(ready and blocks)
        self.bar.destination.setEnabled(ready and blocks)
        self.bar.preview.setEnabled(ready and (blocks or self.bar.content.entities.isChecked()))
        can_apply = ready and bool(window.pending) and window.views.ready
        self.bar.apply.setEnabled(can_apply)
        self.bar.cancel.setEnabled(not window.placement.committing and not (window._job and window._job[0] == "apply"))
        window.menus.actions["apply"].setEnabled(can_apply)
        window.menus.actions["discard"].setEnabled(True)
        if self.plan is not None and window.pending is self.plan.change:
            self.bar.info.setText(self.plan.summary + " · one Undo")
        else:
            self.bar.info.setText("Repeat selection · original stays")
        self.bar.reposition()
