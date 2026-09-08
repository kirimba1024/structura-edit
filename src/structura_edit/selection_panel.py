from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGridLayout, QLabel, QPushButton, QSpinBox, QVBoxLayout, QWidget


class SelectionPanel(QWidget):
    bounds_requested = Signal(object, object)
    all_requested = Signal()
    clear_requested = Signal()

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        self.info = QLabel("No selection")
        layout.addWidget(self.info)
        grid = QGridLayout()
        grid.addWidget(QLabel("From"), 1, 0)
        grid.addWidget(QLabel("To (exclusive)"), 2, 0)
        self.fields = [[], []]
        for axis, name in enumerate("XYZ"):
            grid.addWidget(QLabel(name), 0, axis + 1)
            for row in range(2):
                field = QSpinBox()
                field.setKeyboardTracking(False)
                field.valueChanged.connect(self._changed)
                self.fields[row].append(field)
                grid.addWidget(field, row + 1, axis + 1)
        self.setFocusProxy(self.fields[0][0])
        layout.addLayout(grid)
        all_button = QPushButton("Select all")
        all_button.clicked.connect(self.all_requested)
        layout.addWidget(all_button)
        clear = QPushButton("Clear selection")
        clear.clicked.connect(self.clear_requested)
        layout.addWidget(clear)

    def set_document(self, size):
        for row, values in zip(self.fields, ((0, 0, 0), size)):
            for field, limit, value in zip(row, size, values):
                field.blockSignals(True)
                field.setRange(0, limit)
                field.setValue(value)
                field.blockSignals(False)

    def set_selection(self, selection):
        self.info.setText("No selection" if selection is None else
                          " × ".join(str(hi - lo) for lo, hi in zip(selection.lower, selection.upper))
                          + f" · {selection.volume:,} cells")
        if selection is not None:
            for row, values in zip(self.fields, (selection.lower, selection.upper)):
                for field, value in zip(row, values):
                    field.blockSignals(True)
                    field.setValue(value)
                    field.blockSignals(False)

    def _changed(self):
        self.bounds_requested.emit(*(tuple(field.value() for field in row) for row in self.fields))
