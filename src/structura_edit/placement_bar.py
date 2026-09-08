from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QSizePolicy, QSpinBox, QToolButton, QVBoxLayout, QWidget

from .appearance import GRID


class PlacementBar(QWidget):
    position_changed = Signal(object)
    follow_changed = Signal(bool)
    air_changed = Signal(bool)
    apply_requested = Signal()
    cancel_requested = Signal()

    def __init__(self, plotter):
        super().__init__(plotter)
        self.setObjectName("placementBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_LayoutOnEntireRect)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self.selection = QWidget()
        self.actions = QHBoxLayout(self.selection)
        self.actions.setContentsMargins(0, 0, 0, 0)
        self.actions.setSpacing(4)
        self.size_label = QLabel()
        self.actions.addWidget(self.size_label)
        self.placement = QWidget()
        layout = QVBoxLayout(self.placement)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        row = QHBoxLayout()
        self.info = QLabel()
        row.addWidget(self.info)
        self.follow = QCheckBox("Follow cursor")
        self.follow.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.follow.toggled.connect(self.follow_changed)
        self.air = QCheckBox("Air")
        self.air.setToolTip("Include air and omitted cells; overwrite destination blocks")
        self.air.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.air.toggled.connect(self.air_changed)
        row.addWidget(self.follow)
        row.addWidget(self.air)
        self.apply = self._button("Apply", self._apply)
        self.apply.setToolTip("Apply locally (Enter)")
        self.cancel = self._button("Cancel", self.cancel_requested)
        self.cancel.setToolTip("Cancel placement (Escape)")
        row.addWidget(self.apply)
        row.addWidget(self.cancel)
        row.addStretch()
        layout.addLayout(row)
        row = QHBoxLayout()
        self.coordinates = []
        for axis in "XYZ":
            field = QSpinBox()
            field.setRange(-30_000_000, 30_000_000)
            field.setKeyboardTracking(False)
            field.setAccessibleName(f"Placement {axis}")
            field.setFixedWidth(124)
            field.valueChanged.connect(self._coordinates_changed)
            row.addWidget(QLabel(axis))
            row.addWidget(field)
            self.coordinates.append(field)
        keys = QLabel("Arrows: XZ · Shift: Y")
        keys.setToolTip("Left / Right: X · Up / Down: Z · Shift + Up / Down: Y")
        row.addWidget(keys)
        row.addStretch()
        layout.addLayout(row)
        self.hint = QLabel()
        self.hint.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        layout.addWidget(self.hint)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(GRID, GRID, GRID, GRID)
        layout.setSpacing(0)
        layout.addWidget(self.selection)
        layout.addWidget(self.placement)
        self.hide()

    def _button(self, text, signal):
        button = QToolButton()
        button.setText(text)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.clicked.connect(signal)
        return button

    def bind_actions(self, actions):
        for name in ("copy", "take", "duplicate", "paste", "export"):
            button = QToolButton()
            actions[name].setIconText(name.capitalize())
            button.setDefaultAction(actions[name])
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self.actions.addWidget(button)
        self.actions.addStretch()

    def _coordinates_changed(self):
        self.position_changed.emit(tuple(field.value() for field in self.coordinates))

    def _apply(self):
        for field in self.coordinates:
            field.interpretText()
        self.apply_requested.emit()

    def update_state(self, model, session, selection, *, busy, visible):
        self.setVisible(visible and (model is not None or selection is not None))
        self.selection.setVisible(model is None)
        self.placement.setVisible(model is not None)
        if model is None:
            if selection is not None:
                self.size_label.setText("×".join(str(hi - lo) for lo, hi in zip(selection.lower, selection.upper)))
        else:
            reason = model.reason(session)
            size = "×".join(map(str, model.clipboard.size))
            self.info.setText(f"{'Take' if model.take else 'Paste'} · {size}")
            self.info.setToolTip(self.info.text())
            for widget, value in ((self.follow, model.following), (self.air, model.include_air)):
                widget.blockSignals(True)
                widget.setChecked(value)
                widget.blockSignals(False)
                widget.setEnabled(not busy)
            for field, value in zip(self.coordinates, model.position):
                field.blockSignals(True)
                if not field.hasFocus():
                    field.setValue(value)
                field.blockSignals(False)
                field.setEnabled(not busy)
            self.apply.setEnabled(not busy and not reason)
            self.hint.setText(reason or ("Click to pin · Enter applies locally" if model.following
                                        else "Pinned · XYZ / arrows adjust · Enter applies"))
            self.hint.setToolTip(self.hint.text())
        self.updateGeometry()
