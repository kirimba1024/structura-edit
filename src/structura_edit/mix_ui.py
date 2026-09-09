from PySide6.QtCore import Qt, QStringListModel
from PySide6.QtWidgets import (
    QCompleter, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox,
    QVBoxLayout, QWidget,
)

from .appearance import CONTROL_HEIGHT, GRID, PANEL_WIDTH
from .controls import CellLabel
from .mix import Mix


class MixDialog(QDialog):
    def __init__(self, parent, mix=None, materials=None):
        super().__init__(parent)
        self.setWindowTitle("Material mix")
        self.setFixedWidth(PANEL_WIDTH)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(GRID * 2, GRID * 2, GRID * 2, GRID * 2)
        layout.setSpacing(GRID)
        self.materials = QStringListModel(self)
        if materials:
            self.materials.setStringList(list(materials))
        self.rows = []
        for state, weight in (mix.items if mix else (("minecraft:stone", 3), ("minecraft:cobblestone", 1))):
            layout.addWidget(self._row(state, weight))
        add = QPushButton("Add material")
        add.clicked.connect(lambda: layout.insertWidget(layout.indexOf(add), self._row("", 1)))
        layout.addWidget(add)
        seed_row = QWidget()
        seed_layout = QHBoxLayout(seed_row)
        seed_layout.setContentsMargins(0, 0, 0, 0)
        seed_layout.setSpacing(GRID)
        self.seed = QSpinBox(minimum=0, maximum=999_999, accessibleName="Seed")
        self.seed.setValue(mix.seed if mix else 0)
        seed_layout.addWidget(CellLabel("Seed"))
        seed_layout.addWidget(self.seed)
        seed_layout.addStretch(1)
        layout.addWidget(seed_row)
        self.summary = CellLabel()
        layout.addWidget(self.summary)
        self.error = QLabel()
        self.error.setFixedHeight(CONTROL_HEIGHT)
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Use mix")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.sync()

    def _row(self, state, weight):
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(GRID)
        material = QLineEdit(state, placeholderText="minecraft:stone")
        completer = QCompleter(self.materials, material)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        material.setCompleter(completer)
        material.textChanged.connect(self.sync)
        share = QSpinBox(minimum=1, maximum=999, accessibleName="Weight")
        share.setValue(weight)
        share.valueChanged.connect(self.sync)
        remove = QPushButton("Remove")
        remove.clicked.connect(lambda: (self.rows.remove(row), row.setParent(None), self.sync()))
        layout.addWidget(material, stretch=1)
        layout.addWidget(share)
        layout.addWidget(remove)
        self.rows.append(row)
        return row

    def build(self):
        items = tuple((row.findChild(QLineEdit).text().strip(), row.findChild(QSpinBox).value())
                      for row in self.rows if row.findChild(QLineEdit).text().strip())
        return Mix(items, self.seed.value())

    def sync(self):
        try:
            mix = self.build()
            total = mix.total
            shares = " · ".join(f"{state.removeprefix('minecraft:')} {weight * 100 // total}%"
                                for state, weight in mix.items)
            self.summary.setText(shares)
            self.error.setText("")
        except ValueError as failure:
            self.summary.setText("")
            self.error.setText(str(failure))

    def done(self, result):
        if result == QDialog.DialogCode.Accepted:
            try:
                self.mix = self.build()
            except ValueError as failure:
                self.error.setText(str(failure))
                return
        super().done(result)


def choose_mix(parent, mix=None, materials=None):
    dialog = MixDialog(parent, mix, materials)
    if dialog.exec() == QDialog.DialogCode.Accepted:
        return dialog.mix
    return mix
