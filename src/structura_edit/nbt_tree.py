from itertools import islice

from amulet_nbt import CompoundTag
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem


from .nbt_values import ARRAY_VALUES, CONTAINERS, at_path, path_text, replace_value, value_summary


PAGE_SIZE = 128


class NbtTree(QTreeWidget):
    value_requested = Signal(object)
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.root = None
        self.setHeaderLabels(["Name / index", "Type", "Value"])
        self.setColumnWidth(0, 260)
        self.setColumnWidth(1, 100)
        self.setUniformRowHeights(True)
        self.itemExpanded.connect(self.populate)
        self.itemDoubleClicked.connect(self.activate)

    def set_root(self, root):
        self.clear()
        self.root = root
        item = self._item("Object", (), root)
        self.addTopLevelItem(item)
        item.setExpanded(True)

    def _item(self, name, path, value):
        container = isinstance(value, CONTAINERS)
        item = QTreeWidgetItem([name, type(value).__name__.removesuffix("Tag"), value_summary(value)])
        item.setData(0, Qt.ItemDataRole.UserRole, path)
        item.setToolTip(0, path_text(path))
        if container and len(value):
            item.addChild(QTreeWidgetItem(["Loading…"]))
            item.setData(1, Qt.ItemDataRole.UserRole, 0)
        return item

    def populate(self, item):
        offset = item.data(1, Qt.ItemDataRole.UserRole)
        if offset is None:
            return
        path = item.data(0, Qt.ItemDataRole.UserRole)
        value = at_path(self.root, path)
        item.takeChild(item.childCount() - 1)
        keys = value.keys() if isinstance(value, CompoundTag) else range(len(value))
        stop = min(len(value), offset + PAGE_SIZE)
        shown = {item.child(i).data(0, Qt.ItemDataRole.UserRole) for i in range(item.childCount())}
        for key in islice(keys, offset, stop):
            if (*path, key) in shown:
                continue
            child = value[key]
            if type(value) in ARRAY_VALUES:
                child = ARRAY_VALUES[type(value)](int(child))
            item.addChild(self._item(str(key), (*path, key), child))
        item.setData(1, Qt.ItemDataRole.UserRole, stop if stop < len(keys) else None)
        if stop < len(keys):
            more = QTreeWidgetItem([f"Load next {PAGE_SIZE}…"])
            more.setData(2, Qt.ItemDataRole.UserRole, True)
            item.addChild(more)

    def activate(self, item, column=0):
        if item.data(2, Qt.ItemDataRole.UserRole):
            self.populate(item.parent())
        else:
            self.value_requested.emit(item.data(0, Qt.ItemDataRole.UserRole))

    def value(self, path):
        return at_path(self.root, path)

    def replace_value(self, path, value):
        root = replace_value(self.root, path, value)
        item = self.currentItem()
        self.set_root(root)
        if item is not None or path:
            self.reveal(path)
        self.changed.emit()

    def reveal(self, path):
        item = self.topLevelItem(0)
        for depth, key in enumerate(path):
            item.setExpanded(True)
            child_path = path[:depth + 1]
            child = next((item.child(i) for i in range(item.childCount())
                          if item.child(i).data(0, Qt.ItemDataRole.UserRole) == child_path), None)
            if child is None:
                child = self._item(str(key), child_path, self.value(child_path))
                item.insertChild(0, child)
            item = child
        self.setCurrentItem(item)
        item.setExpanded(True)
        self.scrollToItem(item)
        return item
