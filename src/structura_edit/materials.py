from collections import Counter

from PySide6.QtCore import QEvent, QPoint, QSettings, QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QIcon, QTextOption
from PySide6.QtWidgets import QComboBox, QHeaderView, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QTreeView, QVBoxLayout, QWidget

from .appearance import CONTROL_HEIGHT, GRID
from .material_model import MaterialModel
from .local_store import storage_root


RECENT_LIMIT = 12


class MaterialsPanel(QWidget):
    chosen = Signal(str)
    dismissed = Signal()

    def __init__(self):
        super().__init__()
        self.counts = Counter()
        self.settings = QSettings(str(storage_root() / "preferences.ini"), QSettings.Format.IniFormat)
        self.recent = self.settings.value("materials/recent", [], type=list)[:RECENT_LIMIT]
        self.catalog = {}
        self.icons = None
        self.catalog_request = lambda: None
        layout = QVBoxLayout(self)
        self.scope = QComboBox()
        self.scope.addItems(["Catalog", "In build", "Recent"])
        self.scope.currentIndexChanged.connect(self.reload)
        layout.addWidget(self.scope)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Find material…")
        self.setFocusProxy(self.search)
        layout.addWidget(self.search)
        self.model = MaterialModel(self)
        self.filtered = QSortFilterProxyModel(self)
        self.filtered.setSourceModel(self.model)
        self.filtered.setFilterKeyColumn(0)
        self.filtered.setFilterRole(Qt.ItemDataRole.UserRole + 1)
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
        hint = QLabel("Catalog uses the chosen resources.\nI / middle click: pick To")
        self.hint = hint
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.search.textChanged.connect(self._filter)
        self.search.returnPressed.connect(self._choose)
        for widget in (self.search, self.table, self.detail, self.use):
            widget.installEventFilter(self)
        self.reload()

    @property
    def states(self):
        return list(dict.fromkeys((*self.recent, *self.counts, *self.catalog)))

    def remember(self, state):
        self.recent = [state, *(value for value in self.recent if value != state)][:RECENT_LIMIT]
        self.settings.setValue("materials/recent", self.recent)
        if self.isVisible():
            self.reload()

    def set_catalog(self, result, version):
        self.catalog = result["rows"]
        actual = result["version"]
        self.hint.setText("Choose a material, then preview the change.")
        self.hint.setToolTip(result["source"] + f"\nResources DV {actual or 'unknown'} · Document DV {version}"
                             + ("\nResource version differs; IDs are not converted." if actual and actual != version else ""))
        self.reload()

    def set_counts(self, counts):
        self.counts = counts
        if self.isVisible():
            self.reload()

    def reload(self):
        selected = self.table.currentIndex().siblingAtColumn(0).data(Qt.ItemDataRole.UserRole)
        states = self.states if self.scope.currentIndex() == 0 else self.counts if self.scope.currentIndex() == 1 else self.recent
        self.model.set_rows([(state, self.catalog.get(state.split("[", 1)[0], state.removeprefix("minecraft:")), self.counts[state]) for state in states])
        self.table.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        widest = f"{max(self.counts.values(), default=0):,}"
        self.table.header().resizeSection(1, max(self.fontMetrics().horizontalAdvance(widest), self.fontMetrics().horizontalAdvance("Loaded")) + GRID * 5)
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

    def request_icons(self):
        if self.icons is None or not self.isVisible():
            return
        first = max(0, self.table.indexAt(QPoint(1, 1)).row())
        identifiers = []
        for row in range(first, min(first + 24, self.filtered.rowCount())):
            index = self.filtered.index(row, 0)
            identifier = index.data(Qt.ItemDataRole.UserRole).split("[", 1)[0]
            identifiers.append(identifier)
            if identifier not in self.model.icons:
                pixmap = self.icons.pixmap(identifier)
                if pixmap is not None:
                    self.model.set_icon(self.filtered.mapToSource(index), identifier, QIcon(pixmap))
        self.icons.request(identifiers)

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
