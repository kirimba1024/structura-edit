from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt, Signal
from PySide6.QtWidgets import QLabel, QListView, QVBoxLayout, QWidget


class HistoryModel(QAbstractListModel):
    def __init__(self, parent):
        super().__init__(parent)
        self.history = None

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() or self.history is None else len(self.history.entries) + 1

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or self.history is None or role != Qt.ItemDataRole.DisplayRole:
            return None
        row = index.row()
        if row == 0:
            return "0 · Opened document"
        entry = self.history.entries[row - 1]
        return f"{row} · {entry.label} · {entry.cells:,} blocks"


class HistoryPanel(QWidget):
    requested = Signal(int)

    def __init__(self):
        super().__init__()
        self.key = None
        self.model = HistoryModel(self)
        self.list = QListView()
        self.list.setModel(self.model)
        self.list.setUniformItemSizes(True)
        self.list.clicked.connect(lambda index: self.requested.emit(index.row()))
        self.info = QLabel("Click a step to restore that state")
        layout = QVBoxLayout(self)
        layout.addWidget(self.info)
        layout.addWidget(self.list)

    def set_session(self, session, *, busy=False):
        history = session.history if session else None
        key = (session._id, len(history.entries), history.cursor,
               history.entries[-1].key if history.entries else None) if session else None
        self.list.setEnabled(not busy)
        if key == self.key:
            return
        self.key = key
        self.model.beginResetModel()
        self.model.history = history
        self.model.endResetModel()
        if history is not None:
            self.list.setCurrentIndex(self.model.index(history.cursor, 0))
            self.list.scrollTo(self.model.index(history.cursor, 0))
            self.info.setText(f"{history.cursor} applied · {len(history.entries) - history.cursor} to redo")
