from PySide6.QtCore import QAbstractTableModel, QEvent, QModelIndex, Qt, Signal
from PySide6.QtWidgets import QAbstractItemView, QHBoxLayout, QHeaderView, QLineEdit, QComboBox, QSizePolicy, QToolButton, QTreeView, QVBoxLayout, QWidget

from .appearance import CONTROL_HEIGHT, GRID, PANEL_WIDTH
from .controls import CellCheckBox, CellLabel


class ObjectResults(QAbstractTableModel):
    def __init__(self, parent):
        super().__init__(parent)
        self.rows = ()
        self.origin = (0, 0, 0)

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else 2

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return ("Object", "Type")[section]

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return (row.name, "Entity" if row.kind == "entity" else "Block")[index.column()]
        if role in (Qt.ItemDataRole.ToolTipRole, Qt.ItemDataRole.AccessibleTextRole):
            position = " · ".join(f"{axis} {value + origin:g}" for axis, value, origin in zip("XYZ", row.position, self.origin))
            return f"{row.identity}\n{position}"

    def replace(self, rows, origin):
        self.beginResetModel()
        self.rows, self.origin = rows, origin
        self.endResetModel()


class ObjectSearchPanel(QWidget):
    changed = Signal()
    requested = Signal(str)
    page_requested = Signal(int)
    dismissed = Signal()

    def __init__(self, plotter):
        super().__init__(plotter)
        self.setObjectName("objectSearch")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoMousePropagation)
        self.setFixedWidth(PANEL_WIDTH)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(GRID, GRID, GRID, GRID)
        layout.setSpacing(GRID)
        title = QHBoxLayout()
        title.setSpacing(GRID)
        title.addWidget(CellLabel("Find objects"), 1)
        close = self.button("×", self.dismissed.emit)
        close.setFixedWidth(CONTROL_HEIGHT)
        close.setAccessibleName("Close object search")
        title.addWidget(close)
        layout.addLayout(title)
        self.search = QLineEdit()
        self.search.setMaxLength(256)
        self.search.setPlaceholderText("Name or ID…")
        self.search.setToolTip("Find by block or entity ID; spaces separate words. Examples: chest, armor stand, mymod:")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.changed)
        self.search.returnPressed.connect(self.changed)
        search_row = QHBoxLayout()
        search_row.setSpacing(GRID)
        search_row.addWidget(self.search, 1)
        self.find = self.button("Find", self.changed.emit)
        search_row.addWidget(self.find)
        layout.addLayout(search_row)
        filters = QHBoxLayout()
        filters.setSpacing(GRID)
        self.kind = QComboBox()
        for text, kind in (("All objects", "all"), ("Entities", "entities"), ("Blocks", "blocks"), ("Block data", "data")):
            self.kind.addItem(text, kind)
        self.kind.setToolTip("Blocks with data includes any block carrying NBT, including modded containers")
        self.kind.setMinimumWidth(0)
        self.kind.currentIndexChanged.connect(self.changed)
        self.in_selection = CellCheckBox("In selection")
        self.in_selection.setToolTip("Search only inside the selected region, including hidden objects")
        self.in_selection.toggled.connect(self.changed)
        filters.addWidget(self.kind, 1)
        filters.addWidget(self.in_selection, 1)
        layout.addLayout(filters)
        self.model = ObjectResults(self)
        self.results = QTreeView()
        self.results.setModel(self.model)
        self.results.setRootIsDecorated(False)
        self.results.setUniformRowHeights(True)
        self.results.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.results.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.results.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.results.header().setStretchLastSection(False)
        self.results.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.results.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.results.setColumnWidth(1, GRID * 20)
        self.results.doubleClicked.connect(lambda: self.requested.emit("show"))
        layout.addWidget(self.results, 1)
        self.identity = CellLabel("Choose an object")
        self.position = CellLabel()
        layout.addWidget(self.identity)
        layout.addWidget(self.position)
        actions = QHBoxLayout()
        actions.setSpacing(GRID)
        self.actions = {name: self.button(name.title(), lambda checked=False, n=name: self.requested.emit(n))
                        for name in ("show", "select", "inspect")}
        for button in self.actions.values():
            actions.addWidget(button)
        layout.addLayout(actions)
        pages = QHBoxLayout()
        pages.setSpacing(GRID)
        self.previous = self.button("‹", lambda: self.page_requested.emit(-1))
        self.previous.setAccessibleName("Previous results")
        self.next = self.button("›", lambda: self.page_requested.emit(1))
        self.next.setAccessibleName("Next results")
        self.info = CellLabel("Loaded area")
        self.info.setToolTip("Search covers loaded data, including objects hidden by the current height slice")
        for button in (self.previous, self.next):
            button.setFixedWidth(CONTROL_HEIGHT)
        pages.addWidget(self.previous)
        pages.addWidget(self.info, 1)
        pages.addWidget(self.next)
        layout.addLayout(pages)
        self.setFocusProxy(self.search)
        for widget in (self, self.search, self.kind, self.in_selection, self.results):
            widget.installEventFilter(self)
        plotter.installEventFilter(self)
        self.hide()

    def button(self, text, callback):
        button = QToolButton()
        button.setText(text)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        button.clicked.connect(callback)
        return button

    def selected(self):
        return [self.model.rows[index.row()] for index in self.results.selectionModel().selectedRows()]

    def reposition(self, bottom=0):
        self.resize(PANEL_WIDTH, min(560, max(280, self.parentWidget().height() - bottom - GRID * 2)))
        self.move(GRID, GRID)
        self.raise_()

    def eventFilter(self, watched, event):
        if watched is self.parentWidget() and event.type() == QEvent.Type.Resize:
            self.reposition()
        if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
            self.dismissed.emit()
            return True
        return super().eventFilter(watched, event)
