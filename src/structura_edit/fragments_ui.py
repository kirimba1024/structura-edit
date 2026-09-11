from pathlib import Path

from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QInputDialog, QLabel, QLineEdit, QListWidget, QSpinBox, QVBoxLayout


class FragmentController(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window

    def save(self):
        window = self.window
        selection = window.document.selected.current
        if selection is None or window.tasks.busy:
            return
        window.navigation.stop()
        name, accepted = QInputDialog.getText(window, "Save fragment", "Name:")
        if not accepted or not name.strip():
            return
        dialog = QDialog(window)
        dialog.setWindowTitle("Fragment details")
        layout = QFormLayout(dialog)
        tags = QLineEdit(placeholderText="windows, stone")
        layout.addRow("Tags", tags)
        anchors = []
        for axis, lo, hi in zip("XYZ", selection.lower, selection.upper):
            field = QSpinBox(minimum=0, maximum=hi - lo - 1)
            field.setValue(0 if axis == "Y" else (hi - lo) // 2)
            layout.addRow("Anchor " + axis, field)
            anchors.append(field)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        if dialog.exec():
            window.tasks.submit("fragment_save", lambda path: window.status.setText("Fragment saved to the local library"),
                                session=window.document.session.fork(), selection=selection, name=name,
                                tags=tags.text().split(","), anchor=tuple(field.value() for field in anchors))

    def show(self):
        window = self.window
        if window.tasks.busy:
            return
        window.navigation.stop()
        def listed(rows):
            dialog = QDialog(window)
            dialog.setWindowTitle("Local fragments")
            dialog.resize(480, 480)
            layout = QVBoxLayout(dialog)
            search = QLineEdit(placeholderText="Find a name or tag…")
            items = QListWidget()
            thumbnail = QLabel()
            thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
            thumbnail.setFixedHeight(128)
            for row in rows:
                items.addItem(row["name"] + " · " + ", ".join(row["tags"]))
            def filter_rows(text):
                for index in range(items.count()):
                    items.item(index).setHidden(text.lower() not in items.item(index).text().lower())
            def selected(index):
                thumbnail.setPixmap(QPixmap(str(Path(rows[index]["path"]) / "thumbnail.png")) if index >= 0 else QPixmap())
            search.textChanged.connect(filter_rows)
            items.currentRowChanged.connect(selected)
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Open | QDialogButtonBox.StandardButton.Cancel)
            buttons.button(QDialogButtonBox.StandardButton.Open).setText("Place")
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            for widget in (search, items, thumbnail, buttons):
                layout.addWidget(widget)
            if rows:
                items.setCurrentRow(0)
            buttons.button(QDialogButtonBox.StandardButton.Open).setEnabled(bool(rows))
            if dialog.exec() and items.currentRow() >= 0:
                window.tasks.submit("fragment_load", loaded, path=rows[items.currentRow()]["path"])
        def loaded(clipboard):
            window.placement.clipboard = clipboard
            window._sync()
            window.placement.start("paste")
        window.tasks.submit("fragment_list", listed)
