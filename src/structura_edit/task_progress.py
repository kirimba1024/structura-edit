from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QProgressBar, QToolButton, QVBoxLayout, QWidget

from .appearance import ACCENT, BORDER, CONTROL_HEIGHT, GRID, PANEL_BACKGROUND, PANEL_PRESSED, PANEL_WIDTH, PROGRESS_DELAY_MS
from .controls import CellLabel

class TaskProgress(QWidget):
    cancelled = Signal()
    visibility_changed = Signal()

    def __init__(self):
        super().__init__()
        self.setFixedSize(PANEL_WIDTH, CONTROL_HEIGHT * 2 + GRID)
        self.label = CellLabel()
        self.count = CellLabel(width=GRID * 40)
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
        layout.setSpacing(GRID)
        title = QHBoxLayout()
        title.setSpacing(GRID)
        title.addWidget(self.label, 1)
        title.addWidget(self.cancel)
        amount = QHBoxLayout()
        amount.setSpacing(GRID * 2)
        amount.addWidget(self.bar, 1)
        amount.addWidget(self.count)
        layout.addLayout(title)
        layout.addLayout(amount)
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
        self.label.setText(label)
        width = self.count.fontMetrics().horizontalAdvance(f"{total:,}/{total:,}") + GRID * 4
        self.count.setFixedWidth(min(PANEL_WIDTH - GRID * 12, max(GRID * 40, (width + GRID - 1) // GRID * GRID)))
        self.count.setText(f"{done:,}/{total:,}" if total else "")
        self.bar.setRange(0, total)
        self.bar.setValue(done)

    def finish(self):
        self.delay.stop()
        self.hide()

    def event(self, event):
        result = super().event(event)
        if event.type() in (QEvent.Type.ShowToParent, QEvent.Type.HideToParent):
            self.visibility_changed.emit()
        return result


class TaskProgressPanel(QWidget):
    def __init__(self, parent, rows):
        super().__init__(parent)
        self.rows = rows
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setObjectName("taskProgressPanel")
        self.setStyleSheet(f"#taskProgressPanel {{ background: {PANEL_BACKGROUND}; border: 1px solid {BORDER}; }}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(GRID * 2, GRID * 2, GRID * 2, GRID * 2)
        layout.setSpacing(GRID * 2)
        for row in rows:
            layout.addWidget(row)
            row.hide()
            row.visibility_changed.connect(self.sync)
        parent.installEventFilter(self)
        self.hide()

    def sync(self):
        visible = any(not row.isHidden() for row in self.rows)
        self.setVisible(visible)
        if visible:
            self.layout().activate()
            self.adjustSize()
            self.move(GRID * 2, max(0, self.parentWidget().height() - self.height() - GRID * 2))
            self.raise_()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Resize:
            self.sync()
        return super().eventFilter(watched, event)
