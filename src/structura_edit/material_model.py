from collections import OrderedDict

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt


class MaterialModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []
        self.icons = OrderedDict()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else 2

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return ("Material", "Loaded")[section]

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        state, name, count = self.rows[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return name if index.column() == 0 else f"{count:,}" if count else "—"
        if role in (Qt.ItemDataRole.UserRole, Qt.ItemDataRole.ToolTipRole):
            return state
        if role == Qt.ItemDataRole.UserRole + 1:
            return name + " " + state
        if role == Qt.ItemDataRole.DecorationRole and index.column() == 0:
            return self.icons.get(state.split("[", 1)[0])
        if role == Qt.ItemDataRole.TextAlignmentRole and index.column() == 1:
            return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter

    def set_rows(self, rows):
        if rows == self.rows:
            return
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def set_icon(self, index, identifier, icon):
        if identifier not in self.icons:
            self.icons[identifier] = icon
            while len(self.icons) > 512:
                self.icons.popitem(last=False)
            self.dataChanged.emit(self.index(0, 0), self.index(len(self.rows) - 1, 0), [Qt.ItemDataRole.DecorationRole])
