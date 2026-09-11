from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt, QTimer, Signal
from PySide6.QtWidgets import QApplication, QComboBox, QHBoxLayout, QListView, QPushButton, QVBoxLayout, QWidget

from .controls import MessageLabel


class HistoryModel(QAbstractListModel):
    def __init__(self, parent):
        super().__init__(parent)
        self.rows = []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return row[0]
        if role == Qt.ItemDataRole.ToolTipRole:
            return row[1]
        if role == Qt.ItemDataRole.UserRole:
            return row[2]


class HistoryPanel(QWidget):
    requested = Signal(int)

    def __init__(self):
        super().__init__()
        self.key = None
        self.audit = None
        self.session = None
        self.busy = False
        self.model = HistoryModel(self)
        self.scope = QComboBox()
        self.scope.addItems(['All actions', 'Edits', 'Errors'])
        self.scope.currentIndexChanged.connect(self.refresh)
        self.list = QListView()
        self.list.setModel(self.model)
        self.list.setUniformItemSizes(True)
        self.list.selectionModel().currentChanged.connect(self.describe)
        self.info = MessageLabel('Select an action to see details. Only edits can be restored.')
        self.restore = QPushButton('Restore this state', enabled=False)
        self.restore.clicked.connect(self.restore_selected)
        copy = QPushButton('Copy details')
        copy.clicked.connect(lambda: QApplication.clipboard().setText(self.list.currentIndex().data(Qt.ItemDataRole.ToolTipRole) or ''))
        layout = QVBoxLayout(self)
        layout.addWidget(self.scope)
        layout.addWidget(self.list, 1)
        layout.addWidget(self.info)
        row = QHBoxLayout()
        row.addWidget(self.restore)
        row.addWidget(copy)
        layout.addLayout(row)
        self.timer = QTimer(self)
        self.timer.setInterval(200)
        self.timer.timeout.connect(lambda: self.refresh() if self.isVisible() else None)
        self.timer.start()

    def set_session(self, session, *, busy=False):
        self.session, self.busy = session, busy
        if self.isVisible():
            self.refresh()
        self.describe()

    def refresh(self, *args):
        session = self.session
        history = session.history if session else None
        key = (session._id, len(history.entries), history.cursor, history.entries[-1].key if history.entries else None) if session else None
        key = key, self.scope.currentIndex(), self.audit.version if self.audit else 0
        if key == self.key:
            return
        self.key = key
        rows = []
        if self.scope.currentIndex() == 1 and history is not None:
            rows.append(('0 · Opened document', 'Restore the document before its first edit.', 0))
            for index, entry in enumerate(history.entries, 1):
                text = f'{index} · {entry.label} · {entry.cells:,} blocks'
                rows.append((text, text + '\nRestore this state uses the existing Undo history.', index))
        elif self.audit:
            targets = {entry.key: index for index, entry in enumerate(history.entries, 1)} if history else {}
            for record in self.audit.records.values():
                if self.scope.currentIndex() == 2 and record['status'] != 'Failed':
                    continue
                duration = f" · {record['seconds']:g}s" if 'seconds' in record else ''
                text = f"{record['time'][11:19]} · {record['label']} · {record['status']}{duration}"
                detail = '\n'.join((text, *(f'{key}: {value}' for key, value in record['details'].items()), record.get('error', '')))
                target = targets.get(record.get('undo_key')) if session and record.get('document') == session._id else None
                rows.append((text, detail, target))
        selected = self.list.currentIndex().row()
        self.model.beginResetModel()
        self.model.rows = rows
        self.model.endResetModel()
        if rows:
            self.list.setCurrentIndex(self.model.index(min(max(selected, 0), len(rows) - 1), 0))
        self.describe()

    def describe(self, *args):
        index = self.list.currentIndex()
        target = index.data(Qt.ItemDataRole.UserRole)
        self.restore.setEnabled(target is not None and self.session is not None and not self.busy)
        self.info.setText(index.data(Qt.ItemDataRole.ToolTipRole) or 'Select an action to see details. Only edits can be restored.')
        if self.audit:
            self.info.setToolTip(self.audit.error or f'Local diagnostic log: {self.audit.directory}\nUp to 20 MiB on disk; 2,000 recent actions in this window.')

    def restore_selected(self):
        target = self.list.currentIndex().data(Qt.ItemDataRole.UserRole)
        if self.restore.isEnabled() and target is not None:
            self.requested.emit(target)
