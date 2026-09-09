from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QSizePolicy, QSpinBox, QToolButton, QVBoxLayout, QWidget

from .appearance import GRID
from .controls import CellCheckBox, CellLabel
from .selection_stats_ui import SelectionStats
from .overlay_bar import OverlayBar
from .destination_ui import DestinationButton
from .clipboard_content_ui import ClipboardContent


class PlacementBar(OverlayBar):
    position_changed = Signal(object)
    follow_changed = Signal(bool)
    air_changed = Signal(bool)
    repeat_changed = Signal(bool)
    apply_requested = Signal()
    cancel_requested = Signal()
    transform_requested = Signal(int, object)
    adjust_requested = Signal()

    def __init__(self, plotter):
        super().__init__(plotter)
        self.narrow = None
        self.setObjectName("placementBar")
        self.selection = QWidget()
        self.actions = QHBoxLayout(self.selection)
        self.actions.setContentsMargins(0, 0, 0, 0)
        self.actions.setSpacing(GRID)
        self.size_label = CellLabel()
        self.size_label.setMinimumWidth(GRID * 20)
        self.actions.addWidget(self.size_label, 1)
        self.stats = SelectionStats()
        self._create_placement()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(GRID, GRID, GRID, GRID)
        layout.setSpacing(0)
        layout.addWidget(self.selection)
        layout.addWidget(self.stats)
        layout.addWidget(self.placement)

    def _create_placement(self):
        self.placement = QWidget()
        layout = QGridLayout(self.placement)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(GRID)
        for column in range(12):
            layout.setColumnStretch(column, 1)
        self.info = CellLabel()
        layout.addWidget(self.info, 0, 0, 1, 4)
        self.follow = CellCheckBox("Follow cursor", toolTip="Follow the cursor · click in the scene to pin the preview",
                                   accessibleName="Follow cursor", focusPolicy=Qt.FocusPolicy.NoFocus)
        self.follow.toggled.connect(self.follow_changed)
        self.air = CellCheckBox("Copy air", toolTip="Include air and omitted cells; overwrite destination blocks",
                                focusPolicy=Qt.FocusPolicy.NoFocus)
        self.air.toggled.connect(self.air_changed)
        self.repeat = CellCheckBox("Keep placing",
                                   toolTip="Keep this copy ready after placing; each placement can be undone",
                                   focusPolicy=Qt.FocusPolicy.NoFocus)
        self.repeat.toggled.connect(self.repeat_changed)
        layout.addWidget(self.follow, 0, 4, 1, 3)
        self.adjust = self._button("Adjust", self.adjust_requested)
        self.adjust.setMinimumWidth(self.follow.sizeHint().width())
        layout.addWidget(self.adjust, 0, 4, 1, 3)
        self.adjust.hide()
        layout.addWidget(self.repeat, 0, 7, 1, 3)
        self.apply = self._button("Place", lambda: self._submit(self.apply_requested))
        self.apply.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.apply.setMinimumWidth(GRID * 32)
        self.apply.setToolTip("Apply locally (Enter)")
        self.cancel = self._button("Cancel", self.cancel_requested)
        self.cancel.setToolTip("Cancel placement (Escape)")
        layout.addWidget(self.apply, 0, 10)
        layout.addWidget(self.cancel, 0, 11)
        self._create_options(layout)

    def _create_options(self, layout):
        self.details = QWidget()
        details = QGridLayout(self.details)
        details.setContentsMargins(0, 0, 0, 0)
        details.setSpacing(GRID)
        for column in range(4):
            details.setColumnStretch(column, 1)
        self.coordinates = []
        for column, axis in enumerate("XYZ"):
            field = QSpinBox(minimum=-30_000_000, maximum=30_000_000, keyboardTracking=False,
                             accessibleName=f"Placement {axis}", prefix=axis + " ", minimumWidth=0)
            field.valueChanged.connect(self._coordinates_changed)
            details.addWidget(field, 0, column)
            self.coordinates.append(field)
        keys = CellLabel("Arrows · Shift ↑↓: Y")
        keys.setToolTip("Left / Right: X · Up / Down: Z · Shift + Up / Down: Y")
        details.addWidget(self.air, 0, 3)
        details.addWidget(keys, 1, 2, 1, 2)
        self.hint = CellLabel()
        self.transforms = []
        for text, turns, flip in (("−90°", -1, None), ("+90°", 1, None), ("Flip X", 0, "x"), ("Flip Z", 0, "z")):
            button = self._button(text, lambda checked=False, t=turns, f=flip: self._submit(self.transform_requested, t, f))
            button.setToolTip(f"Mirror on {flip.upper()}" if flip else f"Rotate {turns * 90:+}° around Y · + is clockwise from above")
            self.transforms.append(button)
            if flip:
                details.addWidget(button, 1, len(self.transforms) - 3)
            else:
                layout.addWidget(button, 1, (len(self.transforms) - 1) * 2, 1, 2)
        self.more = self._button("Options…", lambda: None)
        self.more.setToolTip("Exact X / Y / Z, Flip X / Z and Copy air")
        self.more.setCheckable(True)
        self.more.toggled.connect(self.details.setVisible)
        self.destination = DestinationButton()
        layout.addWidget(self.more, 1, 4, 1, 2)
        layout.addWidget(self.destination, 1, 6, 1, 3)
        layout.addWidget(self.hint, 1, 9, 1, 3)
        self.details.hide()
        self.content = ClipboardContent()
        layout.addWidget(self.content, 2, 0, 1, 12)
        layout.addWidget(self.details, 3, 0, 1, 12)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        narrow = self.width() < GRID * 224
        if not hasattr(self, "destination") or narrow == self.narrow:
            return
        self.narrow = narrow
        positions = ((0, 0, 4), (0, 4, 4), (0, 4, 4), (0, 8, 4), (2, 6, 3), (2, 9, 3),
                     (1, 4, 3), (1, 7, 5), (2, 0, 6)) if narrow else (
                     (0, 0, 4), (0, 4, 3), (0, 4, 3), (0, 7, 3), (0, 10, 1), (0, 11, 1),
                     (1, 4, 2), (1, 6, 3), (1, 9, 3))
        widgets = (self.info, self.follow, self.adjust, self.repeat, self.apply, self.cancel,
                   self.more, self.destination, self.hint)
        layout = self.placement.layout()
        for widget, (row, column, span) in zip(widgets, positions):
            layout.addWidget(widget, row, column, 1, span)
        layout.addWidget(self.content, 3 if narrow else 2, 0, 1, 12)
        layout.addWidget(self.details, 4 if narrow else 3, 0, 1, 12)

    def _button(self, text, signal):
        button = QToolButton(text=text)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.clicked.connect(signal)
        return button

    def bind_actions(self, actions):
        for name in ("copy", "take", "duplicate", "paste", "repeat", "export", "entity_all", "inspect"):
            button = QToolButton()
            actions[name].setIconText({"entity_all": "Entities", "inspect": "Inspect"}.get(name, name.capitalize()))
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

    def update_state(self, model, session, selection, *, busy, visible, review=None, review_ready=False):
        self.setVisible(visible and (model is not None or selection is not None))
        self.selection.setVisible(model is None)
        self.placement.setVisible(model is not None)
        if model is None:
            if selection is not None:
                self.size_label.setText("×".join(str(hi - lo) for lo, hi in zip(selection.lower, selection.upper)))
        else:
            locked = busy or review is not None
            reason = model.reason(session)
            size = "×".join(map(str, model.clipboard.size))
            self.info.setText(f"{'Take' if model.take else 'Paste'} · {size}")
            self.info.setToolTip(self.info.text())
            self.content.set_clipboard(model.clipboard)
            self.content.set_values(model.include_blocks, model.include_entities)
            self.content.setEnabled(not locked)
            for widget, value in ((self.follow, model.following), (self.air, model.include_air), (self.repeat, model.keep_placing)):
                widget.blockSignals(True)
                widget.setChecked(value)
                widget.blockSignals(False)
                widget.setEnabled(not locked)
            self.air.setEnabled(not locked and model.include_blocks)
            for field, value in zip(self.coordinates, model.position):
                field.blockSignals(True)
                if not field.hasFocus():
                    field.setValue(value)
                field.blockSignals(False)
                field.setEnabled(not locked)
            self.destination.set_rule(model.destination)
            self.destination.setEnabled(not locked and model.include_blocks)
            self.follow.setVisible(review is None)
            self.adjust.setVisible(review is not None)
            self.adjust.setEnabled(not busy)
            self.apply.setText("Preview" if model.destination.mode != "all" and review is None else "Place")
            self.apply.setToolTip("Build a filtered preview (Enter)" if model.destination.mode != "all" and review is None
                                 else "Place the preview locally (Enter)")
            self.apply.setEnabled(not busy and not reason and (review is None or (review_ready and bool(review.change))))
            for button in self.transforms:
                button.setEnabled(not locked)
            self.hint.setText(reason or (review.summary if review else "Click a spot · Preview" if model.destination.mode != "all"
                                        else "Click a spot, then Place" if model.following else "Drag X / Y / Z to move"))
            self.hint.setToolTip(self.hint.text())
        self.reposition()
