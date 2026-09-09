from amulet_nbt import from_snbt
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QHBoxLayout, QLineEdit, QPlainTextEdit,
    QPushButton, QStackedWidget, QTabWidget, QVBoxLayout,
)

from .appearance import GRID
from .controls import CellLabel
from .nbt_search_ui import NbtResults, NbtSearch
from .nbt_tree import NbtTree
from .nbt_value_dialog import NbtValueDialog
from .nbt_values import path_text, replace_value


class ObjectInspector(QDialog):
    requested = Signal(object)

    def __init__(self, parent, records, *, readonly=False):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle("Object inspector")
        self.resize(960, 660)
        self.records, self.readonly = records, readonly
        self.index, self.tab_index = -1, 0
        self.drafts = {}
        self.originals = {}
        self.errors = CellLabel()
        self.searcher = NbtSearch(self)
        self.searcher.ready.connect(self.found)
        self.searcher.failed.connect(self.search_failed)
        self.finished.connect(lambda result: self.searcher.shutdown())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*([GRID * 2] * 4))
        layout.setSpacing(GRID)
        self.objects = QComboBox()
        self.objects.addItems([record["title"] for record in records])
        layout.addWidget(self.objects)
        row = QHBoxLayout()
        row.setSpacing(GRID)
        self.search = QLineEdit(clearButtonEnabled=True, maxLength=256, accessibleName="Find in object")
        self.find = QPushButton("Find")
        self.search.textChanged.connect(lambda: self.refresh_search())
        self.search.returnPressed.connect(lambda: self.refresh_search(immediate=True))
        self.find.clicked.connect(lambda: self.refresh_search(immediate=True))
        row.addWidget(self.search, 1)
        row.addWidget(self.find)
        layout.addLayout(row)
        self._create_tabs(layout)
        self._create_actions(layout)
        self.objects.currentIndexChanged.connect(self.choose)
        self.choose(0)

    def _create_actions(self, layout):
        row = QHBoxLayout()
        row.setSpacing(GRID)
        self.path = CellLabel("Select a field or item")
        self.open_value = QPushButton("Edit value…")
        self.open_value.clicked.connect(self.open_selected)
        self.edit_count = QPushButton("Edit count…")
        self.edit_count.clicked.connect(self.change_count)
        row.addWidget(self.path, 1)
        row.addWidget(self.open_value)
        row.addWidget(self.edit_count)
        layout.addLayout(row)
        layout.addWidget(self.errors)
        row = QHBoxLayout()
        row.setSpacing(GRID)
        row.addWidget(CellLabel("Read only" if self.readonly else "Undo available after Apply"), 1)
        self.apply = QPushButton("Apply changes", enabled=not self.readonly)
        self.apply.clicked.connect(self.submit)
        close = QPushButton("Close" if self.readonly else "Cancel")
        close.clicked.connect(self.close)
        row.addWidget(self.apply)
        row.addWidget(close)
        layout.addLayout(row)
        for button in self.find, self.open_value, self.edit_count, self.apply, close:
            button.setAutoDefault(False)

    def _create_tabs(self, layout):
        self.tabs = QTabWidget()
        self.tabs.setObjectName("nbtTabs")
        self.tree = NbtTree()
        self.tree.value_requested.connect(self.edit_value)
        self.tree.changed.connect(self.changed)
        self.tree.itemSelectionChanged.connect(self.sync_actions)
        self.fields = NbtResults()
        self.items = NbtResults(items=True)
        self.inventory = self.items.table
        self.structure = QStackedWidget()
        self.structure.addWidget(self.tree)
        self.structure.addWidget(self.fields)
        self.tabs.addTab(self.structure, "Structure")
        self.tabs.addTab(self.items, "Inventories")
        self.text = QPlainTextEdit(readOnly=self.readonly)
        self.tabs.addTab(self.text, "NBT text")
        self.tabs.currentChanged.connect(self.change_tab)
        layout.addWidget(self.tabs, 1)
        for results in (self.fields, self.items):
            results.page_requested.connect(lambda offset: self.refresh_search(offset=offset, immediate=True))
            results.selection_changed.connect(self.sync_actions)
            results.activated.connect(lambda match: self.open_selected())

    def remember(self):
        if self.index >= 0:
            if self.tab_index == 2 and self.text.document().isModified():
                root = replace_value(self.tree.root, (), from_snbt(self.text.toPlainText()))
                self.tree.set_root(root)
                self.text.document().setModified(False)
            self.drafts[self.index] = self.tree.root

    def choose(self, index):
        try:
            self.remember()
        except Exception as error:
            self.errors.setText(str(error))
            self.objects.blockSignals(True)
            self.objects.setCurrentIndex(self.index)
            self.objects.blockSignals(False)
            return
        self.index = index
        if index not in self.originals:
            record = self.records[index]
            self.originals[index] = record["root"] if "root" in record else from_snbt(record["text"])
        self.tree.set_root(self.drafts.get(index, self.originals[index]))
        self.errors.setText("" if self.readonly else "Changes stay here until Apply · Cancel discards them")
        if self.tab_index == 2:
            self.text.setPlainText(self.tree.root.to_snbt(indent=2))
        self.refresh_search()

    def change_tab(self, index):
        try:
            self.remember()
        except Exception as error:
            self.errors.setText(str(error))
            self.tabs.blockSignals(True)
            self.tabs.setCurrentIndex(self.tab_index)
            self.tabs.blockSignals(False)
            return
        self.tab_index = index
        if index == 2:
            self.text.setPlainText(self.tree.root.to_snbt(indent=2))
        self.errors.setText("" if self.readonly else "Changes stay here until Apply · Cancel discards them")
        self.refresh_search()

    def refresh_search(self, *, offset=0, immediate=False):
        items = self.tab_index == 1
        self.search.setEnabled(self.tab_index != 2)
        self.find.setEnabled(self.tab_index != 2)
        self.search.setPlaceholderText("Find an item by ID or path…" if items else "Find a field or value…")
        self.structure.setCurrentIndex(1 if self.search.text().strip() else 0)
        self.searcher.clear()
        if self.tab_index != 2 and (items or self.search.text().strip()):
            self.results().reset()
            self.searcher.request(self.tree.root, self.search.text(), items=items, offset=offset, immediate=immediate)
        self.sync_actions()

    def results(self):
        return self.items if self.tab_index == 1 else self.fields

    def found(self, page):
        self.results().show_page(page)
        if self.tab_index == 1:
            self.tabs.setTabText(1, f"Inventories ({page.total:,}{'+' if page.limited else ''})")
        self.sync_actions()

    def search_failed(self, message):
        self.results().reset("Search unavailable")
        self.errors.setText(message)

    def selected_path(self):
        if self.tab_index == 2:
            return None
        if self.tab_index == 1 or self.structure.currentIndex() == 1:
            match = self.results().selected()
            return match.path if match is not None else None
        item = self.tree.currentItem()
        return item.data(0, Qt.ItemDataRole.UserRole) if item is not None else None

    def sync_actions(self):
        if not hasattr(self, "open_value"):
            return
        path = self.selected_path()
        items = self.tab_index == 1
        self.path.setText(path_text(path) if path is not None else "Select a field or item")
        self.open_value.setText("Open item…" if items else "View value…" if self.readonly else "Edit value…")
        self.open_value.setEnabled(path is not None)
        self.edit_count.setVisible(items and not self.readonly)
        self.edit_count.setEnabled(path is not None)

    def open_selected(self):
        path = self.selected_path()
        if path is None:
            return
        if self.tab_index == 1:
            self.search.clear()
            self.tabs.setCurrentIndex(0)
            self.tree.reveal(path)
            self.tree.setFocus()
        else:
            self.edit_value(path)

    def change_count(self):
        match = self.items.selected()
        if match is not None:
            self.edit_value(match.count_path)

    def edit_value(self, path):
        if path is None:
            return
        dialog = NbtValueDialog(self, path, self.tree.value(path), readonly=self.readonly,
                                validate=lambda value: replace_value(self.tree.root, path, value))
        if dialog.exec() and not self.readonly:
            self.tree.replace_value(path, dialog.value)
        if QApplication.applicationState() == Qt.ApplicationState.ApplicationActive:
            self.activateWindow()
        target = self.search if self.tab_index == 1 or self.search.text() else self.tree
        target.setFocus()

    def changed(self):
        self.errors.setText("Change ready · Apply to update the document")
        self.refresh_search()

    def submit(self):
        try:
            self.remember()
            changes = [({key: value for key, value in self.records[index].items() if key not in ("root", "text")}, root)
                       for index, root in self.drafts.items()
                       if root != self.originals[index]]
            if changes:
                self.requested.emit(changes)
            else:
                self.errors.setText("No data changes")
        except Exception as error:
            self.errors.setText(str(error))
