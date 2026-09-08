from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QSizePolicy, QSpinBox, QToolButton, QVBoxLayout, QWidget

from .appearance import GRID
from .controls import CellCheckBox, CellLabel
from .selection_stats_ui import SelectionStats


class PlacementBar(QWidget):
    position_changed = Signal(object)
    follow_changed = Signal(bool)
    air_changed = Signal(bool)
    apply_requested = Signal()
    cancel_requested = Signal()
    transform_requested = Signal(int, object)

    def __init__(self, plotter):
        super().__init__(plotter)
        self.setObjectName("placementBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_LayoutOnEntireRect)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self.selection = QWidget()
        self.actions = QHBoxLayout(self.selection)
        self.actions.setContentsMargins(0, 0, 0, 0)
        self.size_label = CellLabel()
        self.size_label.setMinimumWidth(GRID * 20)
        self.actions.addWidget(self.size_label, 1)
        self.stats = SelectionStats()
        self.placement = QWidget()
        layout = QGridLayout(self.placement)
        layout.setContentsMargins(0, 0, 0, 0)
        for column in range(8):
            layout.setColumnStretch(column, 1)
        self.info = CellLabel()
        layout.addWidget(self.info, 0, 0, 1, 3)
        self.follow = CellCheckBox("Follow")
        self.follow.setToolTip("Follow the cursor · click in the scene to pin the preview")
        self.follow.setAccessibleName("Follow cursor")
        self.follow.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.follow.toggled.connect(self.follow_changed)
        self.air = CellCheckBox("Air")
        self.air.setToolTip("Include air and omitted cells; overwrite destination blocks")
        self.air.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.air.toggled.connect(self.air_changed)
        layout.addWidget(self.follow, 0, 3, 1, 2)
        layout.addWidget(self.air, 0, 5)
        self.apply = self._button("Apply", lambda: self._submit(self.apply_requested))
        self.apply.setToolTip("Apply locally (Enter)")
        self.cancel = self._button("Cancel", self.cancel_requested)
        self.cancel.setToolTip("Cancel placement (Escape)")
        layout.addWidget(self.apply, 0, 6)
        layout.addWidget(self.cancel, 0, 7)
        self.coordinates = []
        for column, axis in enumerate("XYZ"):
            field = QSpinBox()
            field.setRange(-30_000_000, 30_000_000)
            field.setKeyboardTracking(False)
            field.setAccessibleName(f"Placement {axis}")
            field.setPrefix(axis + " ")
            field.setMinimumWidth(0)
            field.valueChanged.connect(self._coordinates_changed)
            layout.addWidget(field, 1, column * 2, 1, 2)
            self.coordinates.append(field)
        keys = CellLabel("Arrows · ⇧Y")
        keys.setToolTip("Left / Right: X · Up / Down: Z · Shift + Up / Down: Y")
        layout.addWidget(keys, 1, 6, 1, 2)
        self.hint = CellLabel()
        self.transforms = []
        for text, turns, flip in (("−90°", -1, None), ("+90°", 1, None), ("Flip X", 0, "x"), ("Flip Z", 0, "z")):
            button = self._button(text, lambda checked=False, t=turns, f=flip: self._submit(self.transform_requested, t, f))
            button.setToolTip(f"Mirror on {flip.upper()}" if flip else f"Rotate {turns * 90:+}° around Y · + is clockwise from above")
            self.transforms.append(button)
            layout.addWidget(button, 2, len(self.transforms) - 1)
        layout.addWidget(self.hint, 2, 4, 1, 4)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(GRID, GRID, GRID, GRID)
        layout.setSpacing(0)
        layout.addWidget(self.selection)
        layout.addWidget(self.stats)
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
            button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            self.actions.addWidget(button)
        self.actions.addWidget(self.stats.toggle)

    def _coordinates_changed(self):
        self.position_changed.emit(tuple(field.value() for field in self.coordinates))

    def _submit(self, signal, *args):
        for field in self.coordinates:
            field.interpretText()
        signal.emit(*args)

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
            for button in self.transforms:
                button.setEnabled(not busy)
            self.hint.setText(reason or ("Click to pin · Enter" if model.following else "Pinned · Enter applies"))
            self.hint.setToolTip(self.hint.text())
        self.updateGeometry()
