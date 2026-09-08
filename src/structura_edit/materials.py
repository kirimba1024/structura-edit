from collections import Counter

from PySide6.QtCore import QEvent, QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QStandardItem, QStandardItemModel, QTextOption
from PySide6.QtWidgets import QHeaderView, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QTreeView, QVBoxLayout, QWidget

from .appearance import CONTROL_HEIGHT


RECENT_LIMIT = 12


class MaterialsPanel(QWidget):
    chosen = Signal(str)
    dismissed = Signal()

    def __init__(self):
        super().__init__()
        self.counts = Counter()
        self.recent = []
        layout = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Find material…")
        self.setFocusProxy(self.search)
        layout.addWidget(self.search)
        self.model = QStandardItemModel(self)
        self.filtered = QSortFilterProxyModel(self)
        self.filtered.setSourceModel(self.model)
        self.filtered.setFilterKeyColumn(0)
        self.filtered.setFilterRole(Qt.ItemDataRole.UserRole)
        self.filtered.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.table = QTreeView()
        self.table.setModel(self.filtered)
        self.table.setRootIsDecorated(False)
        self.table.setUniformRowHeights(True)
        self.table.header().setStretchLastSection(False)
        self.table.setEditTriggers(QTreeView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTreeView.SelectionBehavior.SelectRows)
        self.table.activated.connect(self._choose)
        self.table.selectionModel().currentChanged.connect(self._describe)
        layout.addWidget(self.table, 1)
        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.detail.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.detail.setFixedHeight(CONTROL_HEIGHT * 3)
        layout.addWidget(self.detail)
        self.use = QPushButton("Use material")
        self.use.clicked.connect(self._choose)
        layout.addWidget(self.use)
        hint = QLabel("Recent first · Loaded counts\nI / middle click: pick To")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.search.textChanged.connect(self._filter)
        self.search.returnPressed.connect(self._choose)
        for widget in (self.search, self.table, self.detail, self.use):
            widget.installEventFilter(self)
        self.reload()

    @property
    def states(self):
        return list(dict.fromkeys((*self.recent, *self.counts)))

    def remember(self, state):
        self.recent = [state, *(value for value in self.recent if value != state)][:RECENT_LIMIT]
        if self.isVisible():
            self.reload()

    def set_counts(self, counts):
        self.counts = counts
        if self.isVisible():
            self.reload()

    def reload(self):
        selected = self.table.currentIndex().siblingAtColumn(0).data(Qt.ItemDataRole.UserRole)
        self.model.clear()
        self.model.setHorizontalHeaderLabels(["Material", "Loaded"])
        states = dict.fromkeys((*self.recent, *(state for state, count in self.counts.most_common())))
        for state in states:
            item = QStandardItem(state.removeprefix("minecraft:"))
            item.setData(state, Qt.ItemDataRole.UserRole)
            item.setToolTip(state)
            count = QStandardItem(f"{self.counts[state]:,}" if self.counts[state] else "—")
            count.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.model.appendRow([item, count])
        self.table.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._filter(self.search.text())
        matches = self.model.match(self.model.index(0, 0), Qt.ItemDataRole.UserRole, selected, 1,
                                   Qt.MatchFlag.MatchExactly) if selected else []
        if matches:
            index = self.filtered.mapFromSource(matches[0])
            if index.isValid():
                self.table.setCurrentIndex(index)

    def _filter(self, text):
        self.filtered.setFilterFixedString(text.strip())
        self.table.setCurrentIndex(self.filtered.index(0, 0))
        self._describe()

    def _describe(self, *args):
        state = self.table.currentIndex().siblingAtColumn(0).data(Qt.ItemDataRole.UserRole)
        self.detail.setPlainText(state or "No match. Enter other block IDs directly in From / To.")
        self.use.setEnabled(bool(state))

    def _choose(self, *args):
        state = self.table.currentIndex().siblingAtColumn(0).data(Qt.ItemDataRole.UserRole)
        if state:
            self.chosen.emit(state)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape:
                self.dismissed.emit()
                return True
            if watched is self.search and event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                step = 1 if event.key() == Qt.Key.Key_Down else -1
                row = max(0, min(self.filtered.rowCount() - 1, self.table.currentIndex().row() + step))
                self.table.setCurrentIndex(self.filtered.index(row, 0))
                return True
        return super().eventFilter(watched, event)
