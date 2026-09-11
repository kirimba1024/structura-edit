from PySide6.QtCore import Qt, QStringListModel
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QCompleter, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from .appearance import CONTROL_HEIGHT, GRID, PANEL_WIDTH
from .condition import Condition
from .controls import CellLabel


KINDS = (("Non-air", "non-air"), ("Air", "air"), ("Materials", "materials"), ("Properties", "properties"), ("Y range", "height"),
         ("Has block entity", "block-entities"), ("All conditions (AND)", "all"), ("Any condition (OR)", "any"))


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
        self.material_add = add
        add.clicked.connect(self.add_entry)
        remove = QPushButton("Remove")
        self.material_remove = remove
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
        self.strict = QCheckBox("Require every property to exist")
        self.strict.setChecked(bool(condition and condition.strict))
        layout.addWidget(self.strict)
        self.height = QWidget()
        heights = QHBoxLayout(self.height)
        heights.setContentsMargins(0, 0, 0, 0)
        self.lower = QSpinBox(minimum=-30_000_000, maximum=30_000_000, prefix="Y ≥ ")
        self.upper = QSpinBox(minimum=-30_000_000, maximum=30_000_000, prefix="Y ≤ ")
        self.lower.setValue(int(condition.values[0]) if condition and condition.kind == "height" else 0)
        self.upper.setValue(int(condition.values[1]) if condition and condition.kind == "height" else 255)
        heights.addWidget(self.lower)
        heights.addWidget(self.upper)
        layout.addWidget(self.height)
        self.children = list(condition.values) if condition and condition.kind in ("all", "any") else []
        self.child_panel = QWidget()
        children = QVBoxLayout(self.child_panel)
        children.setContentsMargins(0, 0, 0, 0)
        self.child_list = QListWidget()
        self.child_list.setFixedHeight(CONTROL_HEIGHT * 3)
        self.child_list.addItems([value.label for value in self.children])
        children.addWidget(self.child_list)
        add_child = QPushButton("Add condition…")
        add_child.clicked.connect(self.add_child)
        children.addWidget(add_child)
        remove_child = QPushButton("Remove condition")
        remove_child.clicked.connect(self.remove_child)
        children.addWidget(remove_child)
        layout.addWidget(self.child_panel)
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
        self.strict.toggled.connect(self.sync)
        self.lower.valueChanged.connect(self.sync)
        self.upper.valueChanged.connect(self.sync)
        self.sync()

    def add_entry(self):
        text = self.pick.text().strip()
        if text and not any(self.entries.item(row).text() == text for row in range(self.entries.count())):
            self.entries.addItem(text)
        self.pick.clear()

    def add_child(self):
        dialog = ConditionDialog(self, materials=self.materials.stringList())
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.children.append(dialog.condition)
            self.child_list.addItem(dialog.condition.label)
            self.sync()

    def remove_child(self):
        index = self.child_list.currentRow()
        if index >= 0:
            self.children.pop(index)
            self.child_list.takeItem(index)
            self.sync()

    def build(self):
        kind = self.kind.currentData()
        if kind in ("all", "any"):
            return Condition(kind, tuple(self.children), negate=self.negate.isChecked())
        if kind == "height":
            return Condition(kind, (str(self.lower.value()), str(self.upper.value())), negate=self.negate.isChecked())
        if kind == "materials":
            values = tuple(self.entries.item(row).text() for row in range(self.entries.count()))
            if not values:
                raise ValueError("Add at least one material")
            return Condition(kind, values, negate=self.negate.isChecked())
        if kind == "properties":
            return Condition(kind, (self.properties.text().strip(),) if self.properties.text().strip() else (),
                             negate=self.negate.isChecked(), strict=self.strict.isChecked())
        return Condition(kind, negate=self.negate.isChecked())

    def sync(self):
        kind = self.kind.currentData()
        self.entries.setVisible(kind == "materials")
        self.pick.setVisible(kind == "materials")
        self.material_add.setVisible(kind == "materials")
        self.material_remove.setVisible(kind == "materials")
        self.properties.setVisible(kind == "properties")
        self.strict.setVisible(kind == "properties")
        self.height.setVisible(kind == "height")
        self.child_panel.setVisible(kind in ("all", "any"))
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
