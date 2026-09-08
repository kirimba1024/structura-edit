from concurrent.futures import ThreadPoolExecutor
from time import monotonic

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QImage, QPixmap, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QListView, QToolButton, QVBoxLayout, QWidget

from .appearance import CONTROL_HEIGHT, GRID
from .controls import CellLabel
from .selection_stats import selection_materials


COUNTS_HINT = "Selected region · current local edits · air excluded · hover a texture for its block name"


class SelectionStats(QWidget):
    def __init__(self):
        super().__init__()
        self.toggle = QToolButton()
        self.toggle.setText("Blocks")
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.toggle.setCheckable(True)
        self.toggle.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.toggle.setToolTip("Show blocks in the selected region")
        self.toggle.setAccessibleName("Selection block counts")
        self.toggle.toggled.connect(self._toggle)
        self.info = CellLabel()
        self.info.setToolTip(COUNTS_HINT)
        self.items = QListView()
        self.items.setFlow(QListView.Flow.LeftToRight)
        self.items.setWrapping(True)
        self.items.setResizeMode(QListView.ResizeMode.Adjust)
        self.items.setMovement(QListView.Movement.Static)
        self.items.setUniformItemSizes(True)
        self.items.setEditTriggers(QListView.EditTrigger.NoEditTriggers)
        self.items.setSelectionMode(QListView.SelectionMode.NoSelection)
        self.items.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.items.setIconSize(QSize(16, 16))
        self.items.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.items.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self.model = QStandardItemModel(self)
        self.items.setModel(self.model)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, GRID, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.info)
        layout.addWidget(self.items)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="selection-stats")
        self.future = None
        self.key = self.ready_key = self.running_key = None
        self.context = None
        self.changed_at = 0
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self._tick)
        self.hide()

    def set_context(self, session, selection, assets, *, visible):
        key = (id(session), session.revision, selection, assets) if session and selection else None
        if key != self.key:
            self.key = key
            self.ready_key = None
            self.context = (session, selection, assets) if key else None
            self.changed_at = monotonic()
            self.model.clear()
            self.info.setText("Counting…" if key else "No selection")
            self.items.hide()
        self.setVisible(visible and key is not None and self.toggle.isChecked())
        if self.isVisible() and self.key != self.ready_key:
            self.timer.start()

    def _toggle(self, expanded):
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        self.toggle.setToolTip(f"{'Hide' if expanded else 'Show'} blocks in the selected region")
        self.setVisible(expanded and self.key is not None)
        if expanded and self.key != self.ready_key:
            self.changed_at = 0
            self.timer.start()

    def _tick(self):
        if self.future is not None and self.future.done():
            future, self.future = self.future, None
            if self.running_key == self.key:
                self.ready_key = self.key
                try:
                    self._show_rows(future.result())
                except Exception as error:
                    self.info.setText("Counts unavailable")
                    self.info.setToolTip(str(error))
        active = self.isVisible() and self.context is not None
        if self.future is None:
            if active and self.key != self.ready_key:
                if monotonic() - self.changed_at >= 0.15:
                    self.running_key = self.key
                    self.future = self.executor.submit(selection_materials, *self.context)
            else:
                self.timer.stop()

    def _show_rows(self, rows):
        self.model.clear()
        width = max((self.fontMetrics().horizontalAdvance(f"{row[1]:,}") for row in rows), default=0) + 16 + GRID * 4
        cell_size = QSize(max(GRID * 20, (width + GRID - 1) // GRID * GRID), CONTROL_HEIGHT)
        self.items.setGridSize(cell_size)
        for name, count, pixels, color in rows:
            if pixels:
                image = QImage(pixels, 16, 16, QImage.Format.Format_RGBA8888).copy()
            else:
                image = QImage(16, 16, QImage.Format.Format_RGB32)
                image.fill(QColor(*color))
            item = QStandardItem(QIcon(QPixmap.fromImage(image)), f"{count:,}")
            item.setSizeHint(cell_size)
            detail = f"{name} · {count:,} blocks" + (" · texture unavailable" if pixels is None else "")
            item.setToolTip(detail)
            item.setData(detail, Qt.ItemDataRole.AccessibleTextRole)
            item.setData(name, Qt.ItemDataRole.UserRole)
            self.model.appendRow(item)
        total = sum(row[1] for row in rows)
        loaded = "loaded " if hasattr(self.context[0], "loaded_chunks") else ""
        self.info.setText(f"{total:,} {loaded}blocks · {len(rows)} types · no air")
        self.info.setToolTip(COUNTS_HINT)
        self.items.setVisible(bool(rows))
        self._fit_rows()

    def _fit_rows(self):
        columns = max(1, (self.width() - GRID * 4) // max(1, self.items.gridSize().width()))
        rows = max(1, min(2, (self.model.rowCount() + columns - 1) // columns))
        self.items.setFixedHeight(rows * CONTROL_HEIGHT + 2)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_rows()

    def shutdown(self):
        self.timer.stop()
        self.executor.shutdown(wait=False, cancel_futures=True)
