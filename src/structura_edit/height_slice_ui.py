from math import floor

from PySide6.QtCore import QObject, Qt, QSignalBlocker, Signal
from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QPushButton, QSpinBox, QToolButton

from .height_slice import HeightSlice


class HeightSliceController(QObject):
    changed = Signal()

    def __init__(self, document, views, navigation):
        super().__init__(navigation)
        self.document, self.views, self.navigation = document, views, navigation
        self.plotter = navigation.camera.plotter
        self.value = HeightSlice()
        self.button = QToolButton(text=self.value.label, toolTip="Height slice · show interiors without changing blocks",
                                  focusPolicy=Qt.FocusPolicy.NoFocus)
        self.button.clicked.connect(self.show)
        self.dialog = QDialog(self.plotter.window(), Qt.WindowType.Tool)
        self.dialog.setWindowTitle("Height slice")
        form = QFormLayout(self.dialog)
        self.mode = QComboBox()
        for label, mode in (("All layers", "all"), ("Up to Y", "below"), ("Single layer", "layer")):
            self.mode.addItem(label, mode)
        self.y = QSpinBox(minimum=-30_000_000, maximum=30_000_000, keyboardTracking=False)
        self.at_camera = QPushButton("Use camera height")
        self.at_camera.clicked.connect(self.use_camera)
        form.addRow("Show", self.mode)
        form.addRow("World Y", self.y)
        form.addRow(self.at_camera)
        note = QLabel("Changes the view only. Editing uses the full selection.")
        note.setWordWrap(True)
        form.addRow(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Reset | QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Reset).setText("Show all")
        buttons.button(QDialogButtonBox.StandardButton.Reset).clicked.connect(lambda: self.mode.setCurrentIndex(0))
        buttons.rejected.connect(self.dialog.close)
        form.addRow(buttons)
        self.mode.currentIndexChanged.connect(self._changed)
        self.y.valueChanged.connect(self._changed)
        self.dialog.finished.connect(lambda: self.plotter.setFocus())

    def reset(self, session):
        with QSignalBlocker(self.mode), QSignalBlocker(self.y):
            self.mode.setCurrentIndex(0)
            self.y.setValue(session.origin[1] + session.size[1] // 2)
        self.value = HeightSlice()
        self.button.setText(self.value.label)
        self.dialog.hide()

    def sync(self, *, available):
        self.button.setVisible(self.document.session is not None)
        self.button.setEnabled(bool(available))
        self.dialog.setEnabled(bool(available))
        self.y.setEnabled(self.value.mode != "all")

    def show(self):
        if self.button.isEnabled():
            self.navigation.suspend()
            self.dialog.show()
            self.dialog.raise_()
            self.dialog.activateWindow()

    def use_camera(self):
        state = self.views.displayed.state if self.views.displayed else self.document.session
        with QSignalBlocker(self.mode), QSignalBlocker(self.y):
            self.y.setValue(floor(self.plotter.camera.position[1] + state.origin[1]))
            if self.mode.currentData() == "all":
                self.mode.setCurrentIndex(1)
        self._changed()

    def _changed(self):
        mode = self.mode.currentData()
        value = HeightSlice() if mode == "all" else HeightSlice(mode, self.y.value())
        if value == self.value:
            return
        self.value = value
        self.button.setText(value.label)
        self.changed.emit()

    def reveal(self, positions):
        low, high = self.value.interval(self.document.session)
        if any(not low <= position[1] < high for position in positions):
            self.mode.setCurrentIndex(0)
