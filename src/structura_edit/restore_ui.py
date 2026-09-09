from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout,
)

from .appearance import CONTROL_HEIGHT, GRID, PANEL_WIDTH


class BackupDialog(QDialog):
    def __init__(self, parent, world, submit, finished):
        super().__init__(parent)
        self.world = str(world)
        self.submit = submit
        self.finished_callback = finished
        self.backups = []
        self.verified = {}
        self.setWindowTitle("Restore backup")
        self.setFixedWidth(PANEL_WIDTH * 3 // 2)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*([GRID * 2] * 4))
        layout.setSpacing(GRID)
        self.table = QTableWidget(0, 3, accessibleName="World backups")
        self.table.setHorizontalHeaderLabels(["Backup", "Files", "Installed"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self.sync)
        layout.addWidget(self.table, 1)
        self.note = QLabel("Backups are written before every world save.\nRestoring first saves the current files.")
        self.note.setFixedHeight(CONTROL_HEIGHT * 2)
        layout.addWidget(self.note)
        row = QHBoxLayout()
        row.setSpacing(GRID)
        self.verify = QPushButton("Verify")
        self.verify.clicked.connect(self.verify_selected)
        self.restore = QPushButton("Restore")
        self.restore.clicked.connect(self.restore_selected)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        row.addWidget(self.verify)
        row.addWidget(self.restore)
        row.addStretch(1)
        row.addWidget(close)
        layout.addLayout(row)
        self.sync()
        self.submit("backups", self.received, world=self.world)

    def received(self, result):
        self.backups = result.get("backups", [])
        self.table.setRowCount(len(self.backups))
        for row, backup in enumerate(self.backups):
            for column, value in enumerate((backup["name"], str(len(backup["files"])), str(backup["installed"]))):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, backup)
                item.setToolTip(backup["path"])
                self.table.setItem(row, column, item)
        self.table.sortItems(0, Qt.SortOrder.DescendingOrder)
        self.sync()

    def selected(self):
        items = self.table.selectedItems()
        return items[0].data(Qt.ItemDataRole.UserRole) if items else None

    def sync(self):
        backup = self.selected()
        self.verify.setEnabled(backup is not None and backup["name"] not in self.verified)
        self.restore.setEnabled(backup is not None and self.verified.get(backup["name"]) is True)

    def verify_selected(self):
        backup = self.selected()
        if backup is None:
            return
        self.note.setText("Verifying hashes…")

        def received(result):
            ok = result.get("verified")
            self.verified[backup["name"]] = ok
            self.note.setText("Hashes match the manifest." if ok else "Backup files no longer match their hashes.")
            self.sync()

        self.submit("backups", received, verify=True, backup=backup["path"])

    def restore_selected(self):
        backup = self.selected()
        if backup is None:
            return
        answer = QMessageBox.question(self, "Restore backup",
                                      f"Restore {len(backup['files'])} files from {backup['name']}?\n"
                                      "The current files are saved to a new backup first.")
        if answer != QMessageBox.StandardButton.Yes:
            return

        def received(result):
            restored = result["restored"]["restored"]
            self.finished_callback(f"Restored {restored} files · press Refresh (F5) to reload the world")
            self.accept()

        self.submit("backups", received, restore=True, world=self.world, backup=backup["path"])


class ConflictsDialog(QDialog):
    def __init__(self, parent, rows):
        super().__init__(parent)
        self.setWindowTitle("World changed on disk")
        self.setFixedWidth(PANEL_WIDTH * 3 // 2)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*([GRID * 2] * 4))
        layout.setSpacing(GRID)
        self.table = QTableWidget(len(rows), 4, accessibleName="Save conflicts")
        self.table.setHorizontalHeaderLabels(["Position", "Patch before", "On disk", "Patch after"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        for row, conflict in enumerate(rows):
            position, before, disk, after = conflict
            values = (" ".join(str(value) for value in position), before, disk, after)
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                self.table.setItem(row, column, item)
        layout.addWidget(self.table, 1)
        note = QLabel("These positions changed on disk after the edit.\n"
                      "Force writes the patch result onto the disk state.")
        note.setFixedHeight(CONTROL_HEIGHT * 2)
        layout.addWidget(note)
        buttons = QDialogButtonBox()
        force = buttons.addButton("Force write shown", QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        force.clicked.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
