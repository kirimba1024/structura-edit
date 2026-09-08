from math import floor

from PySide6.QtCore import QObject, Signal


class SelectionActions(QObject):
    changed = Signal()
    message = Signal(str)
    preview_changed = Signal()

    def __init__(self, model, panel, camera, *, available):
        super().__init__(panel)
        self.model, self.panel, self.camera = model, panel, camera
        self.available = available
        panel.bounds_requested.connect(self.set_bounds)
        panel.adjust_requested.connect(self.adjust)
        panel.preview_requested.connect(self.preview)
        panel.corner_requested.connect(self.at_camera)
        panel.all_requested.connect(self.select_all)
        panel.clear_requested.connect(self.clear)

    def _apply(self, action, *args):
        if not self.available():
            return
        try:
            action(*args)
        except ValueError as error:
            self.panel.set_selection(self.model.region)
            self.panel.hint.setText(str(error))
            self.panel.hint.setToolTip(str(error))
            self.message.emit(str(error))
            return
        self.changed.emit()

    def set_bounds(self, lower, upper):
        self._apply(self.model.set_bounds, lower, upper)

    def select_all(self):
        self._apply(self.model.select_all)

    def clear(self):
        self._apply(self.model.clear)

    def adjust(self, mode, value):
        self._apply(self.model.adjust, mode, value)

    def preview(self, mode, value):
        self.model.preview = None
        self.panel.hint.setText("Selection only · blocks stay" if self.model.region else "Click a block to start")
        if mode and self.available():
            try:
                self.model.preview = self.model.adjusted(mode, value)
            except ValueError as error:
                self.panel.hint.setText(str(error))
            else:
                size = "×".join(str(hi - lo) for lo, hi in zip(self.model.preview.lower, self.model.preview.upper))
                if mode == "grow":
                    self.panel.hint.setText(f"{'Grow' if value > 0 else 'Shrink'} all → {size}")
                else:
                    axis = next(i for i, amount in enumerate(value) if amount)
                    self.panel.hint.setText(f"Shift {'XYZ'[axis]} {value[axis]:+} · blocks stay")
        self.panel.hint.setToolTip(self.panel.hint.text())
        self.preview_changed.emit()

    def at_camera(self, index):
        self._apply(self.model.set_corner, index, tuple(floor(p) for p in self.camera.position))
