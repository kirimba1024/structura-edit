from PySide6.QtCore import Qt, QStringListModel
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QCompleter, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QPushButton, QVBoxLayout,
)

from .appearance import CONTROL_HEIGHT, GRID, PANEL_WIDTH
from .condition import Condition
from .controls import CellLabel


KINDS = (("Non-air", "non-air"), ("Air", "air"), ("Materials", "materials"), ("Properties", "properties"))


class ConditionDialog(QDialog):
    def __init__(self, parent, condition=None, materials=None):
        super().__init__(parent)
        self.setWindowTitle("Condition")
        self.setFixedWidth(PANEL_WIDTH)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(GRID * 2, GRID * 2, GRID * 2, GRID * 2)
        layout.setSpacing(GRID)
        self.kind = QComboBox(accessibleName="Condition kind")
        for label, key in KINDS:
            self.kind.addItem(label, key)
        self.kind.setCurrentIndex(self.kind.findData(condition.kind if condition else "non-air"))
        layout.addWidget(self.kind)
        self.entries = QListWidget(accessibleName="Condition materials")
        self.entries.setFixedHeight(CONTROL_HEIGHT * 3)
        for value in condition.values if condition and condition.kind == "materials" else ():
            self.entries.addItem(value)
        layout.addWidget(self.entries)
        row = QHBoxLayout()
        row.setSpacing(GRID)
        self.materials = QStringListModel(self)
        if materials:
            self.materials.setStringList(list(materials))
        self.pick = QLineEdit(placeholderText="minecraft:stone")
        completer = QCompleter(self.materials, self.pick)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.pick.setCompleter(completer)
        add = QPushButton("Add")
        add.clicked.connect(self.add_entry)
        remove = QPushButton("Remove")
        remove.clicked.connect(lambda: [self.entries.takeItem(self.entries.currentRow())]
                               if self.entries.currentRow() >= 0 else None)
        row.addWidget(self.pick, stretch=1)
        row.addWidget(add)
        row.addWidget(remove)
        layout.addLayout(row)
        self.properties = QLineEdit(placeholderText="facing=north, waterlogged=true")
        if condition and condition.kind == "properties":
            self.properties.setText(", ".join(condition.values))
        layout.addWidget(self.properties)
        self.negate = QCheckBox("Not")
        self.negate.setChecked(bool(condition and condition.negate))
        layout.addWidget(self.negate)
        self.summary = CellLabel()
        layout.addWidget(self.summary)
        self.error = QLabel()
        self.error.setFixedHeight(CONTROL_HEIGHT)
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Use condition")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.kind.currentIndexChanged.connect(self.sync)
        self.entries.model().rowsInserted.connect(self.sync)
        self.entries.model().rowsRemoved.connect(self.sync)
        self.properties.textChanged.connect(self.sync)
        self.negate.toggled.connect(self.sync)
        self.sync()

    def add_entry(self):
        text = self.pick.text().strip()
        if text and not any(self.entries.item(row).text() == text for row in range(self.entries.count())):
            self.entries.addItem(text)
        self.pick.clear()

    def build(self):
        kind = self.kind.currentData()
        if kind == "materials":
            values = tuple(self.entries.item(row).text() for row in range(self.entries.count()))
            if not values:
                raise ValueError("Add at least one material")
            return Condition(kind, values, negate=self.negate.isChecked())
        if kind == "properties":
            return Condition(kind, (self.properties.text().strip(),) if self.properties.text().strip() else (),
                             negate=self.negate.isChecked())
        return Condition(kind, negate=self.negate.isChecked())

    def sync(self):
        kind = self.kind.currentData()
        self.entries.setVisible(kind == "materials")
        self.pick.setVisible(kind == "materials")
        self.properties.setVisible(kind == "properties")
        try:
            self.summary.setText(self.build().label)
            self.error.setText("")
        except ValueError as failure:
            self.summary.setText("")
            self.error.setText(str(failure))

    def done(self, result):
        if result == QDialog.DialogCode.Accepted:
            try:
                self.condition = self.build()
            except ValueError as failure:
                self.error.setText(str(failure))
                return
        super().done(result)


def choose_condition(parent, condition=None, materials=None):
    dialog = ConditionDialog(parent, condition, materials)
    if dialog.exec() == QDialog.DialogCode.Accepted:
        return dialog.condition
    return condition
