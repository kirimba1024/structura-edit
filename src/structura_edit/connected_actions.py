from PySide6.QtCore import QObject, Signal


CRITERIA = {"Material": "material", "Exact state": "state", "Non-air": "non-air"}


class ConnectedActions(QObject):
    changed = Signal()
    message = Signal(str)

    def __init__(self, document, tasks, panel, *, available):
        super().__init__(panel)
        self.document = document
        self.tasks = tasks
        self.panel = panel
        self.available = available
        self.active = False
        self.criterion = "material"
        self.subtract = False
        panel.connected_toggled.connect(self.set_active)
        panel.criterion_changed.connect(self.set_criterion)
        panel.subtract_toggled.connect(self.set_subtract)

    def set_active(self, enabled):
        enabled = bool(enabled)
        if enabled == self.active:
            return
        self.active = enabled
        self.panel.connected.setChecked(enabled)
        self.panel.criterion.setEnabled(enabled)
        self.panel.subtract.setEnabled(enabled)
        self.message.emit("Connected select: click matching blocks · Esc exits" if enabled else "")

    def toggle(self):
        self.set_active(not self.active)

    def set_criterion(self, label):
        self.criterion = CRITERIA.get(label, "material")

    def set_subtract(self, enabled):
        self.subtract = bool(enabled)

    def sync(self):
        if self.active and not self.available():
            self.set_active(False)

    def pick(self, hit):
        if not self.active or not self.available() or self.tasks.busy or hit is None:
            return
        session = self.document.session
        token = self.document.session_token
        criterion, subtract = self.criterion, self.subtract

        def received(result):
            if token != self.document.session_token:
                self.message.emit("The document changed; click again")
                return
            selected = self.document.selected
            before = selected.current.volume if selected.current is not None else 0
            if subtract:
                selected.subtract_cells(result.cells)
            else:
                selected.add_cells(result.cells)
            after = selected.current.volume if selected.current is not None else 0
            verb = "Removed" if subtract else "Added"
            self.message.emit(f"{verb} {abs(after - before):,} cells · {after:,} selected")
            self.changed.emit()

        return self.tasks.submit("connected", received, session=session, start=tuple(hit.position),
                                 criterion=criterion)
