from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import QAbstractButton, QGridLayout, QHBoxLayout, QPushButton, QSpinBox, QToolButton, QVBoxLayout, QWidget

from .appearance import CONTROL_HEIGHT, GRID
from .controls import CellLabel


class SelectionPanel(QWidget):
    bounds_requested = Signal(object, object)
    adjust_requested = Signal(str, object)
    preview_requested = Signal(str, object)
    corner_requested = Signal(int)
    all_requested = Signal()
    clear_requested = Signal()
    dismissed = Signal()

    def __init__(self):
        super().__init__()
        self.origin = (0, 0, 0)
        self.adjust_buttons = {}
        self.preview_button = None
        layout = QVBoxLayout(self)
        self.info = CellLabel("No selection")
        layout.addWidget(self.info)
        grid = QGridLayout()
        self.fields = [[], []]
        for row, name in enumerate(("Min", "Max")):
            label = CellLabel(name)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setToolTip("Block coordinates · both endpoints included")
            grid.addWidget(label, 0, row + 1)
            grid.setColumnStretch(row + 1, 1)
        for axis, name in enumerate("XYZ"):
            label = CellLabel(name, width=CONTROL_HEIGHT)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(label, axis + 1, 0)
            for row in range(2):
                field = QSpinBox()
                field.setKeyboardTracking(False)
                field.setFixedHeight(CONTROL_HEIGHT)
                field.setAccessibleName(f"Selection {'minimum' if row == 0 else 'maximum'} {name}")
                field.valueChanged.connect(self._changed)
                self.fields[row].append(field)
                grid.addWidget(field, axis + 1, row + 1)
        self.setFocusProxy(self.fields[0][0])
        layout.addLayout(grid)
        row = QHBoxLayout()
        row.addWidget(CellLabel("Camera", width=GRID * 21))
        for index, name in enumerate("AB"):
            button = QPushButton(f"Set {name} · {index + 1}")
            button.setToolTip(f"Set corner {name} at the camera's cell, even in empty space · {index + 1}")
            button.clicked.connect(lambda checked=False, i=index: self.corner_requested.emit(i))
            row.addWidget(button)
        layout.addLayout(row)
        self.adjustments = QWidget()
        adjustments = QVBoxLayout(self.adjustments)
        adjustments.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        row.addWidget(CellLabel("Step", width=GRID * 15))
        self.step = QSpinBox()
        self.step.setRange(1, 30_000_000)
        self.step.setKeyboardTracking(False)
        self.step.setMinimumWidth(0)
        self.step.setAccessibleName("Selection adjustment step")
        row.addWidget(self.step, 1)
        for name, sign in (("Grow", 1), ("Shrink", -1)):
            button = QPushButton(name)
            button.setFixedWidth(GRID * (16 if sign > 0 else 22))
            button.setToolTip(f"{name} all six faces by the step · selection bounds only")
            button.clicked.connect(lambda checked=False, s=sign: self._grow(s))
            self.adjust_buttons[button] = ("grow", sign)
            row.addWidget(button)
        adjustments.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(CellLabel("Shift", width=GRID * 18))
        for axis, name in enumerate("XYZ"):
            for sign in (-1, 1):
                button = QToolButton()
                button.setText(name + ("−" if sign < 0 else "+"))
                button.setMinimumWidth(GRID * 9)
                button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
                button.setToolTip(f"Shift bounds {'−' if sign < 0 else '+'}{name} by the step · blocks stay in place")
                button.clicked.connect(lambda checked=False, a=axis, s=sign: self._shift(a, s))
                self.adjust_buttons[button] = ("shift", tuple(sign if i == axis else 0 for i in range(3)))
                row.addWidget(button, 1)
        adjustments.addLayout(row)
        layout.addWidget(self.adjustments)
        self.hint = CellLabel("Click a block to start")
        layout.addWidget(self.hint)
        self.step.valueChanged.connect(lambda: self._preview(self.preview_button))
        row = QHBoxLayout()
        for name, signal in (("Select all", self.all_requested), ("Clear", self.clear_requested)):
            button = QPushButton(name)
            button.clicked.connect(signal)
            row.addWidget(button)
        layout.addLayout(row)
        layout.addStretch()
        for field in (*self.fields[0], *self.fields[1], self.step, *self.findChildren(QAbstractButton)):
            field.installEventFilter(self)

    def set_document(self, size, origin=(0, 0, 0)):
        self.origin = origin
        self.step.setMaximum(max(size))
        for row, values in zip(self.fields, ((0, 0, 0), tuple(s - 1 for s in size))):
            for field, limit, value, offset in zip(row, size, values, origin):
                field.blockSignals(True)
                field.setRange(offset, offset + limit - 1)
                field.setValue(value + offset)
                field.blockSignals(False)

    def set_selection(self, selection):
        self.adjustments.setEnabled(selection is not None)
        self.hint.setText("Selection only · blocks stay" if selection else "Click a block to start")
        self.hint.setToolTip(self.hint.text())
        self.info.setText("No selection" if selection is None else
                          "×".join(str(hi - lo) for lo, hi in zip(selection.lower, selection.upper))
                          + f" · {selection.volume:,} cells")
        if selection is not None:
            values = (selection.lower, tuple(p - 1 for p in selection.upper))
            for row, coordinates in zip(self.fields, values):
                for field, value, offset in zip(row, coordinates, self.origin):
                    field.blockSignals(True)
                    field.setValue(value + offset)
                    field.blockSignals(False)

    def _grow(self, sign):
        self._preview(None)
        self.step.interpretText()
        self.adjust_requested.emit("grow", self.step.value() * sign)

    def _shift(self, axis, sign):
        self._preview(None)
        self.step.interpretText()
        self.adjust_requested.emit("shift", tuple(self.step.value() * sign if i == axis else 0 for i in range(3)))

    def _changed(self):
        self.bounds_requested.emit(tuple(field.value() - offset for field, offset in zip(self.fields[0], self.origin)),
                                   tuple(field.value() - offset + 1 for field, offset in zip(self.fields[1], self.origin)))

    def _dismiss(self):
        for field in (*self.fields[0], *self.fields[1], self.step):
            field.setValue(field.value())
        self._preview(None)
        self.dismissed.emit()

    def _preview(self, button):
        self.preview_button = button
        if button is None:
            self.preview_requested.emit("", None)
            return
        mode, value = self.adjust_buttons[button]
        amount = self.step.value()
        self.preview_requested.emit(mode, value * amount if mode == "grow" else tuple(v * amount for v in value))

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
            self._dismiss()
            return True
        if watched not in self.adjust_buttons:
            return super().eventFilter(watched, event)
        if event.type() in (QEvent.Type.Enter, QEvent.Type.FocusIn):
            self._preview(watched)
        elif event.type() in (QEvent.Type.Leave, QEvent.Type.FocusOut, QEvent.Type.Hide, QEvent.Type.EnabledChange):
            if watched is self.preview_button:
                self._preview(None)
        return super().eventFilter(watched, event)
