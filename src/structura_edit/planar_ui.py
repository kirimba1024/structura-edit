from PySide6.QtCore import QObject


class PlanarController(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.active = False

    def toggle(self):
        self.active = not self.active
        window = self.window
        if not self.active and window.tasks.kind == "planar":
            window.cancel_task()
        window.connected.set_active(False)
        window.menus.actions["planar"].setChecked(self.active)
        window.status.setText("Planar select: click an exposed full-cube face · Esc exits" if self.active else "Planar select off")

    def pick(self, hit):
        window = self.window
        if not self.active or hit is None or window.tasks.busy:
            return
        token = window.document.input_token
        def received(cells):
            if not self.active or token != window.document.input_token:
                return
            window.document.selected.set_cells(cells)
            window._selection_changed()
            self.toggle()
            window.show_operation("Extrude")
            for field, value in zip(window.operation.fields["normal"].inputs, hit.normal):
                field.setValue(value)
        window.tasks.submit("planar", received, session=window.document.session.fork(), start=hit.position, normal=hit.normal)
