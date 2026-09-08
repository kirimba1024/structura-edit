from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHeaderView, QLabel, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget


class MaterialsPanel(QWidget):
    chosen = Signal(str)

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        self.table = QTreeWidget()
        self.setFocusProxy(self.table)
        self.table.setHeaderLabels(["Material", "Count"])
        self.table.setRootIsDecorated(False)
        self.table.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.itemDoubleClicked.connect(self._choose)
        layout.addWidget(self.table)
        layout.addWidget(QLabel("Double-click a material to fill the selected region."))

    def set_counts(self, counts):
        self.table.clear()
        for state, count in counts.most_common():
            item = QTreeWidgetItem([state.removeprefix("minecraft:"), f"{count:,}"])
            item.setData(0, Qt.ItemDataRole.UserRole, state)
            item.setToolTip(0, state)
            self.table.addTopLevelItem(item)

    def _choose(self, item, column):
        self.chosen.emit(item.data(0, Qt.ItemDataRole.UserRole))
