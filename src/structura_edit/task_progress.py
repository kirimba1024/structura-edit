from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QProgressBar, QStackedLayout, QToolButton, QVBoxLayout, QWidget

from .appearance import ACCENT, CONTROL_HEIGHT, GRID, PANEL_PRESSED, PANEL_WIDTH, PROGRESS_DELAY_MS
from .controls import CellLabel


class TaskProgress(QWidget):
    cancelled = Signal()
    visibility_changed = Signal()

    def __init__(self):
        super().__init__()
        self.requested = False
        self.setFixedHeight(CONTROL_HEIGHT + GRID)
        self.setMinimumWidth(GRID * 36)
        self.label = CellLabel()
        self.count = CellLabel(width=GRID * 16)
        self.count.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.bar = QProgressBar()
        self.bar.setFixedHeight(GRID)
        self.bar.setTextVisible(False)
        self.bar.setStyleSheet(f"QProgressBar {{ border: 0; background: {PANEL_PRESSED}; }} "
                              f"QProgressBar::chunk {{ background: {ACCENT}; }}")
        self.cancel = QToolButton()
        self.cancel.setText("×")
        self.cancel.setToolTip("Cancel task")
        self.cancel.setAccessibleName("Cancel task")
        self.cancel.setAutoRaise(True)
        self.cancel.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.cancel.setFixedSize(CONTROL_HEIGHT, CONTROL_HEIGHT)
        self.cancel.clicked.connect(self.cancelled)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        title = QHBoxLayout()
        title.setSpacing(GRID)
        title.addWidget(self.label, 1)
        title.addWidget(self.count)
        title.addWidget(self.cancel)
        layout.addLayout(title)
        layout.addWidget(self.bar)
        self.delay = QTimer(self)
        self.delay.setSingleShot(True)
        self.delay.setInterval(PROGRESS_DELAY_MS)
        self.delay.timeout.connect(self.show)
        self.hide()

    def start(self, label, *, cancellable=True):
        self.set_progress(label, 0, 0)
        self.cancel.setEnabled(cancellable)
        if not self.requested and not self.delay.isActive():
            self.delay.start()

    def show(self):
        self.requested = True
        super().show()
        self.visibility_changed.emit()

    def set_progress(self, label, done, total):
        self.label.setText(label)
        width = self.count.fontMetrics().horizontalAdvance(f"{total:,}/{total:,}") + GRID * 4
        self.count.setFixedWidth(min(PANEL_WIDTH // 2, max(GRID * 16, (width + GRID - 1) // GRID * GRID)))
        self.count.setVisible(bool(total))
        self.count.setText(f"{done:,}/{total:,}" if total else "")
        self.bar.setRange(0, total)
        self.bar.setValue(done)

    def finish(self):
        changed = self.requested
        self.requested = False
        self.delay.stop()
        self.hide()
        if changed:
            self.visibility_changed.emit()


class TaskProgressPanel(QWidget):
    visibility_changed = Signal(bool)

    def __init__(self, parent, rows):
        super().__init__(parent)
        self.rows = rows
        layout = QStackedLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(GRID * 2)
        for row in rows:
            layout.addWidget(row)
            row.hide()
            row.visibility_changed.connect(self.sync)
        self.hide()

    def sync(self):
        selected = next((row for row in self.rows if row.requested), None)
        if selected is not None:
            self.layout().setCurrentWidget(selected)
        for row in self.rows:
            row.setVisible(row is selected)
        self.setVisible(selected is not None)
        self.visibility_changed.emit(selected is not None)
