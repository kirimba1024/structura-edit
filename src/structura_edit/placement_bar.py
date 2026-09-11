from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QMenu, QSizePolicy, QSpinBox, QToolButton, QVBoxLayout, QWidget

from .appearance import GRID
from .controls import CellCheckBox, CellLabel, MessageLabel
from .overlay_bar import OverlayBar
from .destination_ui import DestinationButton
from .clipboard_content_ui import ClipboardContent
from .tool_icons import tool_icon


class PlacementBar(OverlayBar):
    position_changed = Signal(object)
    follow_changed = Signal(bool)
    air_changed = Signal(bool)
    repeat_changed = Signal(bool)
    apply_requested = Signal()
    cancel_requested = Signal()
    transform_requested = Signal(int, object, str)
    adjust_requested = Signal()
    preview_requested = Signal()

    def __init__(self, plotter):
        super().__init__(plotter)
        self.narrow = None
        self.setObjectName("placementBar")
        self.selection = QWidget()
        self.actions = QVBoxLayout(self.selection)
        self.action_widgets = []
        self.actions.setContentsMargins(0, 0, 0, 0)
        self.actions.setSpacing(GRID)
        self.size_label = CellLabel()
        self.size_label.setMinimumWidth(GRID * 20)
        self.size_label.hide()
        self._create_placement()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(GRID, GRID, GRID, GRID)
        layout.setSpacing(0)
        layout.addWidget(self.selection)
        layout.addWidget(self.placement)

    def _create_placement(self):
        self.placement = QWidget()
        layout = QGridLayout(self.placement)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(GRID)
        for column in range(12):
            layout.setColumnStretch(column, 1)
        header = QWidget()
        top = QHBoxLayout(header)
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(GRID)
        layout.addWidget(header, 0, 0, 1, 12)
        self.info = CellLabel()
        top.addWidget(self.info, 1)
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
        top.addWidget(self.follow, 1)
        self.adjust = self._button("Adjust", self.adjust_requested)
        self.adjust.setMinimumWidth(self.follow.sizeHint().width())
        top.addWidget(self.adjust, 1)
        self.adjust.hide()
        self.apply = self._button("Place", lambda: self._submit(self.apply_requested))
        self.apply.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.apply.setFixedWidth(GRID * 24)
        self.apply.setToolTip("Apply locally (Enter)")
        self.cancel = self._button("Cancel", self.cancel_requested)
        self.cancel.setToolTip("Cancel placement (Escape)")
        top.addWidget(self.apply)
        top.addWidget(self.cancel)
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
        self.hint = MessageLabel()
        self.transforms = []
        self.transform_grid = QWidget()
        grid = QGridLayout(self.transform_grid)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(GRID)
        for row, axis in enumerate("XYZ"):
            grid.addWidget(CellLabel(axis, width=GRID * 7), row, 0)
            for column, (text, turns, flip) in enumerate((("−90°", -1, None), ("+90°", 1, None), ("Mirror", 0, axis.lower())), 1):
                button = self._button(text, lambda checked=False, t=turns, f=flip, a=axis.lower(): self._submit(self.transform_requested, t, f, a))
                button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
                button.setToolTip(f"Mirror {axis}" if flip else f"Rotate {turns * 90:+}° around {axis} · + is clockwise when looking from +{axis} toward the origin")
                button.setAccessibleName(button.toolTip())
                self.transforms.append(button)
                grid.addWidget(button, row, column)
        layout.addWidget(self.transform_grid, 1, 0, 3, 4, Qt.AlignmentFlag.AlignLeft)
        self.more = self._button("Options…", lambda: None)
        self.more.setToolTip("Exact position, Copy air and repeated placement")
        self.more.setCheckable(True)
        self.more.toggled.connect(self.details.setVisible)
        self.destination = DestinationButton()
        layout.addWidget(self.more, 1, 4, 1, 2)
        layout.addWidget(self.destination, 1, 6, 1, 6)
        layout.addWidget(self.hint, 2, 4, 2, 8)
        self.details.hide()
        self.content = ClipboardContent()
        layout.addWidget(self.content, 4, 0, 1, 12)
        layout.addWidget(self.details, 5, 0, 1, 12)
        self.preview = self._button("Preview changes", self.preview_requested)
        details.addWidget(self.repeat, 1, 0, 1, 2)
        details.addWidget(self.preview, 2, 0, 1, 4)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "action_widgets"):
            self._layout_actions()

    def _button(self, text, signal):
        button = QToolButton(text=text)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.clicked.connect(signal)
        return button

    def bind_actions(self, actions):
        for name in ("select_tool", "take", "duplicate", "Fill", "Replace", "Erase", "paste", "inspect"):
            button = QToolButton()
            actions[name].setIconText({"select_tool": "Select", "inspect": "Inspect", "take": "Move"}.get(name, name.capitalize()))
            actions[name].setIcon(tool_icon(name))
            button.setDefaultAction(actions[name])
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            button.setIconSize(QSize(16, 16))
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            self.action_widgets.append(button)
        more = QToolButton(text="More…")
        more.setToolTip("Copy to clipboard, repeated copies, export and selection details")
        more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(more)
        menu.setToolTipsVisible(True)
        for name in ("copy", "repeat", "export", "entity_all", "coordinates", "materials"):
            menu.addAction(actions[name])
        more.setMenu(menu)
        self.action_widgets.append(more)
        self._layout_actions()

    def _layout_actions(self):
        while self.actions.count():
            row = self.actions.takeAt(0).layout()
            while row.count():
                row.takeAt(0)
            row.deleteLater()
        available = max(1, self.width() - GRID * 2)
        row, used = None, 0
        for widget in self.action_widgets:
            width = widget.sizeHint().width()
            if row is None or used + width + GRID > available:
                if row is not None:
                    row.addStretch()
                row = QHBoxLayout()
                row.setSpacing(GRID)
                self.actions.addLayout(row)
                used = 0
            row.addWidget(widget)
            used += width + GRID
        if row is not None:
            row.addStretch()

    def _coordinates_changed(self):
        self.position_changed.emit(tuple(field.value() for field in self.coordinates))

    def _submit(self, signal, *args):
        for field in self.coordinates:
            field.interpretText()
        signal.emit(*args)

    def update_state(self, model, session, selection, *, busy, visible, review=None, review_ready=False):
        self.setVisible(visible and session is not None)
        self.selection.setVisible(model is None)
        self.placement.setVisible(model is not None)
        if model is None:
            if selection is not None:
                self.size_label.setText("×".join(str(hi - lo) for lo, hi in zip(selection.lower, selection.upper)))
        else:
            locked = busy or review is not None
            reason = model.reason(session)
            size = "×".join(map(str, model.clipboard.size))
            self.info.setText(f"{'Move' if model.take else 'Copy'} · {size}")
            self.info.setToolTip(self.info.text() + "\n" + ("Original will be removed after Place" if model.take else "Original will stay after Place"))
            self.content.set_clipboard(model.clipboard)
            self.content.set_values(model.include_blocks, model.include_entities)
            self.content.set_rule(model.destination)
            self.content.setEnabled(not locked)
            for widget, value in ((self.follow, model.following), (self.air, model.include_air), (self.repeat, model.keep_placing)):
                widget.blockSignals(True)
                widget.setChecked(value)
                widget.blockSignals(False)
                widget.setEnabled(not locked)
            self.repeat.setVisible(not model.take)
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
            self.apply.setText("Place")
            self.apply.setToolTip("Place here (Enter). Undo removes this placement.")
            self.preview.setEnabled(not locked and not reason)
            self.apply.setEnabled(not busy and not reason and (review is None or (review_ready and bool(review.change))))
            for button in self.transforms:
                button.setEnabled(not locked)
            self.hint.setText(reason or (review.summary if review else "Click to fix the position, then Place."
                                        if model.following else "Drag an axis or enter a position in Options, then Place."))
            self.hint.setToolTip(self.hint.text())
        self.reposition()
