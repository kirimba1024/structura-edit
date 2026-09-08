from math import floor

from PySide6.QtCore import QObject, Qt, QSignalBlocker
from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QPushButton, QSpinBox, QToolButton

from .height_slice import HeightSlice


class HeightSliceController(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.value = HeightSlice()
        self.button = QToolButton()
        self.button.setText(self.value.label)
        self.button.setToolTip("Height slice · show interiors without changing blocks")
        self.button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.button.clicked.connect(self.show)
        window.statusBar().addPermanentWidget(self.button)
        self.dialog = QDialog(window, Qt.WindowType.Tool)
        self.dialog.setWindowTitle("Height slice")
        form = QFormLayout(self.dialog)
        self.mode = QComboBox()
        for label, mode in (("All layers", "all"), ("Up to Y", "below"), ("Single layer", "layer")):
            self.mode.addItem(label, mode)
        self.y = QSpinBox()
        self.y.setRange(-30_000_000, 30_000_000)
        self.y.setKeyboardTracking(False)
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
        self.dialog.finished.connect(lambda: window.plotter.setFocus())

    def reset(self, session):
        with QSignalBlocker(self.mode), QSignalBlocker(self.y):
            self.mode.setCurrentIndex(0)
            self.y.setValue(session.origin[1] + session.size[1] // 2)
        self.value = HeightSlice()
        self.button.setText(self.value.label)
        self.dialog.hide()

    def sync(self):
        window = self.window
        available = window.session is not None and not window.placement.active
        available = available and (not window.worker.busy or (window._job and window._job[0] in ("render", "map")))
        self.button.setVisible(window.session is not None)
        self.button.setEnabled(bool(available))
        self.dialog.setEnabled(bool(available))
        self.y.setEnabled(self.value.mode != "all")
        window.menus.actions["height"].setEnabled(bool(available))

    def show(self):
        if self.button.isEnabled():
            self.window.navigation.suspend()
            self.dialog.show()
            self.dialog.raise_()
            self.dialog.activateWindow()

    def use_camera(self):
        state = self.window.views.displayed.state if self.window.views.displayed else self.window.session
        with QSignalBlocker(self.mode), QSignalBlocker(self.y):
            self.y.setValue(floor(self.window.plotter.camera.position[1] + state.origin[1]))
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
        self.window.overlay.set_hover(None)
        self.window.render_scene()
