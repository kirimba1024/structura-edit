from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox, QGridLayout, QLabel, QSizePolicy, QSpinBox, QToolButton

from .appearance import GRID
from .controls import CellCheckBox, CellLabel
from .overlay_bar import OverlayBar
from .destination_ui import DestinationButton
from .clipboard_content_ui import ClipboardContent


class RepeatBar(OverlayBar):
    changed = Signal()
    preview_requested = Signal()
    apply_requested = Signal()
    cancel_requested = Signal()

    def __init__(self, plotter):
        super().__init__(plotter)
        layout = QGridLayout(self)
        layout.setContentsMargins(GRID, GRID, GRID, GRID)
        layout.setSpacing(GRID)
        self.copies = QSpinBox(minimum=1, maximum=500_000, value=3, keyboardTracking=False,
                               accessibleName="Extra copies")
        self.direction = QComboBox()
        for label, axis, sign in (("Up (+Y)", 1, 1), ("Down (−Y)", 1, -1), ("East (+X)", 0, 1),
                                  ("West (−X)", 0, -1), ("South (+Z)", 2, 1), ("North (−Z)", 2, -1)):
            self.direction.addItem(label, (axis, sign))
        self.direction.setAccessibleName("Copy direction")
        self.gap = QSpinBox(minimum=0, maximum=30_000_000, keyboardTracking=False, accessibleName="Gap in blocks",
                            toolTip="Empty space between copies; 0 places them edge to edge")
        for column, (label, field) in enumerate((("Extra copies", self.copies), ("Direction", self.direction), ("Gap (blocks)", self.gap))):
            title = QLabel(label)
            title.setBuddy(field)
            layout.addWidget(title, 0, column * 2)
            layout.addWidget(field, 0, column * 2 + 1)
            layout.setColumnStretch(column * 2 + 1, 1)
        self.air = CellCheckBox("Copy air",
                                toolTip="Air inside each copy clears destination blocks; gaps remain unchanged")
        layout.addWidget(self.air, 0, 6)
        self.info = CellLabel("Repeat selection · original stays · one Undo")
        layout.addWidget(self.info, 1, 0, 1, 3)
        self.destination = DestinationButton()
        self.destination.changed.connect(self.changed)
        layout.addWidget(self.destination, 1, 3)
        for name, label, signal, column in (("preview", "Preview", self.preview_requested, 4),
                                            ("apply", "Place copies", self.apply_requested, 5),
                                            ("cancel", "Cancel", self.cancel_requested, 6)):
            button = QToolButton(text=label)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.clicked.connect(lambda checked=False, s=signal: self._submit(s))
            layout.addWidget(button, 1, column)
            setattr(self, name, button)
        self.content = ClipboardContent()
        self.content.changed.connect(self.changed)
        self.destination.changed.connect(self.content.set_rule)
        layout.addWidget(self.content, 2, 0, 1, 7)
        self.inputs = (self.copies, self.direction, self.gap, self.air, self.destination, self.content)
        self.copies.valueChanged.connect(self.changed)
        self.direction.currentIndexChanged.connect(self.changed)
        self.gap.valueChanged.connect(self.changed)
        self.air.toggled.connect(self.changed)

    def _submit(self, signal):
        self.copies.interpretText()
        self.gap.interpretText()
        signal.emit()

    def values(self, selection):
        axis, sign = self.direction.currentData()
        distance = selection.upper[axis] - selection.lower[axis] + self.gap.value()
        step = tuple(sign * distance if i == axis else 0 for i in range(3))
        return dict(copies=self.copies.value(), step=step, include_air=self.air.isChecked(), destination=self.destination.rule,
                    **self.content.values())
