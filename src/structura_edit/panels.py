from PySide6.QtCore import Qt, Signal, QStringListModel
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QCompleter, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from .commands import COMMANDS, PARAMETERS, REGION_COMMANDS, UI_COMMANDS
from .appearance import GRID
from .controls import CellCheckBox, CellLabel


class OperationPanel(QWidget):
    changed = Signal()
    material_requested = Signal(str)
    preview_requested = Signal()
    apply_requested = Signal()
    discard_requested = Signal()

    def __init__(self):
        super().__init__()
        self.saved = {}
        self.current = REGION_COMMANDS[0]
        self.fields = {}
        self.materials = QStringListModel(self)
        layout = QVBoxLayout(self)
        self._create_form(layout)
        self.info = CellLabel()
        layout.addWidget(self.info)
        self.preview = QPushButton("Preview")
        self.preview.clicked.connect(self.preview_requested)
        layout.addWidget(self.preview)
        self.apply = QPushButton("Apply")
        self.discard = QPushButton("Discard")
        self.apply.clicked.connect(self.apply_requested)
        self.discard.clicked.connect(self.discard_requested)
        row = QHBoxLayout()
        row.addWidget(self.apply)
        row.addWidget(self.discard)
        layout.addLayout(row)
        self.reset = QPushButton("Reset settings")
        self.reset.clicked.connect(self.reset_settings)
        layout.addWidget(self.reset)
        layout.addStretch()
        self.mode.currentTextChanged.connect(self._mode_changed)
        self.reset_settings()
        self._mode_changed(self.current)

    def _create_form(self, layout):
        self.form = QFormLayout()
        self.form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        self.form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.mode = QComboBox()
        self.mode.addItems(UI_COMMANDS)
        self.mode.insertSeparator(len(REGION_COMMANDS))
        labels = ["Action", *(parameter.label + "…" for parameter in PARAMETERS.values() if isinstance(parameter.default, str))]
        label_width = max(self.fontMetrics().horizontalAdvance(label) for label in labels) + GRID * 4
        label_width = (label_width + GRID - 1) // GRID * GRID
        self.form.addRow(CellLabel("Action", width=label_width), self.mode)
        for key, parameter in PARAMETERS.items():
            field = self._parameter_field(parameter)
            self.fields[key] = field
            if isinstance(parameter.default, (bool, tuple)):
                self.form.addRow(field)
            else:
                button = QPushButton(parameter.label + "…")
                button.setFixedWidth(label_width)
                button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                button.setToolTip("Choose a material from loaded and recent blocks")
                button.clicked.connect(lambda checked=False, name=key: self.material_requested.emit(name))
                self.form.addRow(button, field)
        layout.addLayout(self.form)

    def _parameter_field(self, parameter):
        value = parameter.default
        if isinstance(value, bool):
            field = CellCheckBox(parameter.label)
            field.toggled.connect(self.changed)
        elif isinstance(value, int):
            field = QSpinBox(minimum=1, maximum=16, keyboardTracking=False, accessibleName=parameter.label)
            field.valueChanged.connect(self.changed)
        elif isinstance(value, tuple):
            field = QWidget()
            axes = QVBoxLayout(field)
            axes.setContentsMargins(0, 0, 0, 0)
            field.inputs = []
            for axis in "XYZ":
                number = QSpinBox(minimum=-30_000_000, maximum=30_000_000, keyboardTracking=False, prefix=axis + " ",
                                  accessibleName=f"Offset {axis}")
                number.valueChanged.connect(self.changed)
                field.inputs.append(number)
                axes.addWidget(number)
        else:
            field = QLineEdit()
            completer = QCompleter(self.materials, field)
            completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            completer.setFilterMode(Qt.MatchFlag.MatchContains)
            field.setCompleter(completer)
            field.textChanged.connect(self.changed)
        field.setToolTip(parameter.description)
        return field

    def set_materials(self, states):
        self.materials.setStringList(list(states))

    def values(self):
        result = {}
        for key in COMMANDS[self.current].parameters:
            field = self.fields[key]
            if isinstance(field, QCheckBox):
                result[key] = field.isChecked()
            elif isinstance(field, QLineEdit):
                result[key] = field.text().strip()
            elif isinstance(field, QSpinBox):
                result[key] = field.value()
            else:
                result[key] = tuple(f.value() for f in field.inputs)
        return result

    def set_values(self, values):
        self.blockSignals(True)
        try:
            for key, value in values.items():
                field = self.fields[key]
                if isinstance(field, QCheckBox):
                    field.setChecked(value)
                elif isinstance(field, QLineEdit):
                    field.setText(value)
                    field.setCursorPosition(0)
                elif isinstance(field, QSpinBox):
                    field.setValue(value)
                else:
                    for axis, number in zip(field.inputs, value):
                        axis.setValue(number)
        finally:
            self.blockSignals(False)
        self.changed.emit()

    def reset_settings(self):
        self.set_values(COMMANDS[self.current].defaults())

    def _mode_changed(self, name):
        target = self.fields["target"].text()
        self.saved[self.current] = self.values()
        self.saved[self.current].pop("target", None)
        self.current = name
        for key, field in self.fields.items():
            self.form.setRowVisible(field, key in COMMANDS[name].parameters)
        field = self.fields[COMMANDS[name].parameters[0]]
        self.setFocusProxy(field.inputs[0] if hasattr(field, "inputs") else field)
        values = self.saved.get(name, COMMANDS[name].defaults()).copy()
        values["target"] = target
        self.set_values(values)
        self.info.setText(COMMANDS[name].description)


class CommandSearch(QDialog):
    def __init__(self, parent, entries):
        super().__init__(parent)
        self.setWindowTitle("Find command")
        self.resize(460, 330)
        self.entries = entries
        layout = QVBoxLayout(self)
        self.search = QLineEdit(placeholderText="Command name…")
        self.results = QListWidget()
        self.help = QLabel()
        self.help.setWordWrap(True)
        layout.addWidget(self.search)
        layout.addWidget(self.results)
        layout.addWidget(self.help)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Open | QDialogButtonBox.StandardButton.Cancel)
        layout.addWidget(buttons)
        buttons.accepted.connect(self.run)
        buttons.rejected.connect(self.reject)
        self.results.itemActivated.connect(self.run)
        self.results.currentRowChanged.connect(self.describe)
        self.search.textChanged.connect(self.filter)
        self.filter("")

    def filter(self, query):
        self.matches = [(name, action) for name, action in self.entries if query.casefold() in name.casefold()]
        self.results.clear()
        self.results.addItems([name + ("" if action.isEnabled() else " · unavailable") for name, action in self.matches])
        self.results.setCurrentRow(0)

    def describe(self, row):
        self.help.setText(self.matches[row][1].toolTip() if 0 <= row < len(self.matches) else "No matching commands")

    def run(self, *args):
        row = self.results.currentRow()
        if 0 <= row < len(self.matches) and self.matches[row][1].isEnabled():
            action = self.matches[row][1]
            self.accept()
            action.trigger()
