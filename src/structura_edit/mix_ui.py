import json
from pathlib import Path

from PySide6.QtCore import Qt, QStringListModel
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QCompleter, QFileDialog, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QSpinBox,
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
        rows_widget = QWidget()
        self.rows_layout = QVBoxLayout(rows_widget)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(GRID)
        self.rows_area = QScrollArea()
        self.rows_area.setWidgetResizable(True)
        self.rows_area.setWidget(rows_widget)
        layout.addWidget(self.rows_area)
        for state, weight in (mix.items if mix else (("minecraft:stone", 3), ("minecraft:cobblestone", 1))):
            self.rows_layout.addWidget(self._row(state, weight))
        add = QPushButton("Add material")
        add.clicked.connect(lambda: (self.rows_layout.addWidget(self._row("", 1)), self.sync()))
        layout.addWidget(add)
        seed_row = QWidget()
        seed_layout = QHBoxLayout(seed_row)
        seed_layout.setContentsMargins(0, 0, 0, 0)
        seed_layout.setSpacing(GRID)
        self.seed = QSpinBox(minimum=0, maximum=2**31 - 1, accessibleName="Seed")
        self.seed.setValue(mix.seed if mix else 0)
        seed_layout.addWidget(CellLabel("Seed", width=GRID * 16))
        seed_layout.addWidget(self.seed)
        seed_layout.addStretch(1)
        layout.addWidget(seed_row)
        self.anchor = QComboBox()
        self.anchor.addItems(["local", "world"])
        self.anchor.setCurrentText(mix.anchor if mix else "local")
        self.anchor.setToolTip("Hash coordinates in document space or world space")
        layout.addWidget(self.anchor)
        self.gradient = QCheckBox("Height gradient")
        self.gradient.setChecked(bool(mix and mix.gradient))
        layout.addWidget(self.gradient)
        self.lower = QSpinBox(minimum=-30_000_000, maximum=30_000_000, prefix="Bottom Y ")
        self.upper = QSpinBox(minimum=-30_000_000, maximum=30_000_000, prefix="Top Y ")
        self.lower.setValue(mix.gradient[0] if mix and mix.gradient else 0)
        self.upper.setValue(mix.gradient[1] if mix and mix.gradient else 64)
        layout.addWidget(self.lower)
        layout.addWidget(self.upper)
        presets = QHBoxLayout()
        for text, callback in (("Load preset…", self.load_preset), ("Save preset…", self.save_preset)):
            button = QPushButton(text)
            button.clicked.connect(callback)
            presets.addWidget(button)
        layout.addLayout(presets)
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
        for field in (self.seed, self.lower, self.upper):
            field.valueChanged.connect(self.sync)
        self.anchor.currentTextChanged.connect(self.sync)
        self.gradient.toggled.connect(self.sync)
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
        material.setCursorPosition(0)
        material.setToolTip(state)
        material.textChanged.connect(self.sync)
        share = QSpinBox(minimum=1, maximum=999_999, accessibleName="Weight")
        share.setFixedWidth(GRID * 20)
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
        return Mix(items, self.seed.value(), anchor=self.anchor.currentText(),
                   gradient=(self.lower.value(), self.upper.value()) if self.gradient.isChecked() else ())

    def save_preset(self):
        try:
            mix = self.build()
            path, _ = QFileDialog.getSaveFileName(self, "Save mix preset", "material-mix.json", "Mix preset (*.json)")
            if path:
                Path(path).write_text(json.dumps(mix.preset(), indent=2))
        except (OSError, ValueError) as failure:
            self.error.setText(str(failure))

    def load_preset(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load mix preset", "", "Mix preset (*.json)")
        if not path:
            return
        try:
            if Path(path).stat().st_size > 64_000:
                raise ValueError("Preset exceeds 64 KB")
            mix = Mix.from_preset(json.loads(Path(path).read_text()))
            if mix.seed > 2**31 - 1 or any(weight > 999_999 for _, weight in mix.items):
                raise ValueError("Preset values exceed the dialog range")
            for row in self.rows:
                row.setParent(None)
            self.rows = []
            for index, (state, weight) in enumerate(mix.items):
                self.rows_layout.insertWidget(index, self._row(state, weight))
            self.seed.setValue(mix.seed)
            self.anchor.setCurrentText(mix.anchor)
            self.gradient.setChecked(bool(mix.gradient))
            if mix.gradient:
                self.lower.setValue(mix.gradient[0])
                self.upper.setValue(mix.gradient[1])
            self.sync()
        except (OSError, ValueError, TypeError, KeyError) as failure:
            self.error.setText(str(failure))

    def sync(self):
        if not hasattr(self, "summary"):
            return
        self.rows_area.setFixedHeight((CONTROL_HEIGHT + GRID) * min(5, max(2, len(self.rows))) + GRID)
        self.lower.setVisible(self.gradient.isChecked())
        self.upper.setVisible(self.gradient.isChecked())
        try:
            mix = self.build()
            total = mix.total
            shares = " · ".join(f"{state.removeprefix('minecraft:')} {weight * 100 // total}%"
                                for state, weight in mix.items)
            self.summary.setText((mix.items[0][0].removeprefix("minecraft:") + " → " + mix.items[1][0].removeprefix("minecraft:")) if mix.gradient else shares)
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
