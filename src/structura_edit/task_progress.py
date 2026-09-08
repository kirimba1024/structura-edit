from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QToolButton, QWidget

from .appearance import ACCENT, PANEL_PRESSED, PROGRESS_DELAY_MS

class TaskProgress(QWidget):
    cancelled = Signal()

    def __init__(self):
        super().__init__()
        self.label = QLabel()
        self.bar = QProgressBar()
        self.bar.setFixedSize(90, 4)
        self.bar.setTextVisible(False)
        self.bar.setStyleSheet(f"QProgressBar {{ border: 0; background: {PANEL_PRESSED}; }} "
                              f"QProgressBar::chunk {{ background: {ACCENT}; }}")
        self.cancel = QToolButton()
        self.cancel.setText("×")
        self.cancel.setToolTip("Cancel task")
        self.cancel.setAccessibleName("Cancel task")
        self.cancel.setAutoRaise(True)
        self.cancel.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.cancel.clicked.connect(self.cancelled)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        for widget in (self.label, self.bar, self.cancel):
            layout.addWidget(widget)
        self.delay = QTimer(self)
        self.delay.setSingleShot(True)
        self.delay.setInterval(PROGRESS_DELAY_MS)
        self.delay.timeout.connect(self.show)
        self.hide()

    def start(self, label, *, cancellable=True):
        self.set_progress(label, 0, 0)
        self.cancel.setEnabled(cancellable)
        if self.isHidden() and not self.delay.isActive():
            self.delay.start()

    def set_progress(self, label, done, total):
        self.label.setText(f"{label} {done}/{total}" if total else label)
        self.bar.setRange(0, total)
        self.bar.setValue(done)

    def finish(self):
        self.delay.stop()
        self.hide()
