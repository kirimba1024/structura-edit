from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from .appearance import GRID
from .controls import CellLabel
from .nbt_search import MAX_FIELDS, PAGE_SIZE, find_nbt


class NbtSearch(QObject):
    ready = Signal(object)
    failed = Signal(str)

    def __init__(self, parent):
        super().__init__(parent)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="nbt-search")
        self.future = self.pending = None
        self.cancel = Event()
        self.generation = self.running = 0
        self.changed_at = 0
        self.timer = QTimer(self)
        self.timer.setInterval(25)
        self.timer.timeout.connect(self.tick)

    def request(self, root, text, *, items=False, offset=0, immediate=False):
        self.clear()
        self.pending = (root, text, items, offset)
        self.changed_at = monotonic() - (1 if immediate else 0)
        self.timer.start()

    def clear(self):
        self.generation += 1
        self.cancel.set()
        self.pending = None

    def tick(self):
        if self.future is not None and self.future.done():
            future, self.future = self.future, None
            if self.running == self.generation:
                try:
                    result = future.result()
                    if result is not None:
                        self.ready.emit(result)
                except Exception as error:
                    self.failed.emit(str(error))
        if self.future is None and self.pending is not None and monotonic() - self.changed_at >= 0.2:
            root, text, items, offset = self.pending
            self.pending = None
            self.running = self.generation
            self.cancel = Event()
            self.future = self.executor.submit(find_nbt, root, text, items=items, offset=offset, cancel=self.cancel)
        if self.future is None and self.pending is None:
            self.timer.stop()

    def shutdown(self):
        self.clear()
        self.timer.stop()
        self.executor.shutdown(wait=False, cancel_futures=True)


class NbtResults(QWidget):
    page_requested = Signal(int)
    activated = Signal(object)
    selection_changed = Signal()

    def __init__(self, *, items=False):
        super().__init__()
        self.page = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(GRID)
        self.table = QTreeWidget()
        self.table.setHeaderLabels(["Slot", "Item", "Count", "Path"] if items else ["Path", "Type", "Value"])
        self.table.setRootIsDecorated(False)
        self.table.setUniformRowHeights(True)
        self.table.setColumnWidth(0, 72 if items else 380)
        self.table.setColumnWidth(1, 280 if items else 120)
        self.table.setColumnWidth(2, 88 if items else 260)
        self.table.itemSelectionChanged.connect(self.selection_changed)
        self.table.itemDoubleClicked.connect(lambda item, column: self.activated.emit(self.selected()))
        layout.addWidget(self.table, 1)
        row = QHBoxLayout()
        row.setSpacing(GRID)
        self.previous = QPushButton("Previous")
        self.next = QPushButton("Next")
        self.info = CellLabel()
        self.previous.clicked.connect(lambda: self.page_requested.emit(max(0, self.page.offset - PAGE_SIZE)))
        self.next.clicked.connect(lambda: self.page_requested.emit(self.page.offset + PAGE_SIZE))
        row.addWidget(self.previous)
        row.addWidget(self.info, 1)
        row.addWidget(self.next)
        layout.addLayout(row)
        self.reset()

    def reset(self, message="Searching…"):
        self.page = None
        self.table.clear()
        self.previous.setEnabled(False)
        self.next.setEnabled(False)
        self.info.setText(message)

    def show_page(self, page):
        self.reset()
        self.page = page
        for match in page.rows:
            item = QTreeWidgetItem(list(match.columns))
            item.setData(0, Qt.ItemDataRole.UserRole, match)
            for column, text in enumerate(match.columns):
                item.setToolTip(column, text)
            self.table.addTopLevelItem(item)
        end = page.offset + len(page.rows)
        text = f"{page.offset + 1}–{end} of {page.total:,}" if page.rows else "No matches"
        self.info.setText(text + (" · limited" if page.limited else ""))
        self.info.setToolTip(f"Search stops at {MAX_FIELDS:,} fields or 128 levels. Remaining fields are available in Structure and NBT text."
                             if page.limited else text)
        self.previous.setEnabled(page.offset > 0)
        self.next.setEnabled(end < page.total)

    def selected(self):
        item = self.table.currentItem()
        return item.data(0, Qt.ItemDataRole.UserRole) if item is not None else None
