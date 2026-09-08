from PySide6.QtCore import Qt, Signal, QStringListModel
from PySide6.QtWidgets import QComboBox, QCompleter, QDialog, QDialogButtonBox, QFormLayout, QLabel, QSizePolicy, QToolButton

from .appearance import CONTROL_HEIGHT, GRID, PANEL_WIDTH
from .destination_rule import DestinationRule


class DestinationButton(QToolButton):
    changed = Signal(object)

    def __init__(self):
        super().__init__()
        self.materials = QStringListModel(self)
        self.rule = DestinationRule()
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(GRID * 44)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.clicked.connect(self.choose)
        self.set_rule(self.rule)

    def set_rule(self, rule):
        self.rule = rule
        self.label = "Only " + rule.material.removeprefix("minecraft:") if rule.material else rule.label
        self.fit_text()
        self.setToolTip(rule.material or "Choose which destination blocks may be replaced")
        self.setAccessibleName(rule.label + (": " + rule.material if rule.material else ""))

    def fit_text(self):
        self.setText(self.fontMetrics().elidedText(self.label + "…", Qt.TextElideMode.ElideRight,
                                                   max(0, self.contentsRect().width() - GRID * 3)))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit_text()

    def choose(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Placement rule")
        dialog.setFixedWidth(PANEL_WIDTH)
        layout = QFormLayout(dialog)
        layout.setContentsMargins(GRID * 2, GRID * 2, GRID * 2, GRID * 2)
        layout.setSpacing(GRID)
        mode = QComboBox()
        for label, key in (("Replace all", "all"), ("Keep existing", "air"), ("Only material", "material")):
            mode.addItem(label, key)
        mode.setCurrentIndex(mode.findData(self.rule.mode))
        material = QComboBox()
        material.setEditable(True)
        material.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        material.setModel(self.materials)
        material.setEditText(self.rule.material)
        material.lineEdit().setPlaceholderText("minecraft:stone")
        completer = QCompleter(self.materials, material)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        material.setCompleter(completer)
        material.setMinimumWidth(0)
        material.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        material.setAccessibleName("Destination material")
        layout.addRow("Replace", mode)
        layout.addRow("Material", material)
        note = QLabel()
        note.setFixedHeight(CONTROL_HEIGHT * 2)
        layout.addRow(note)
        error = QLabel()
        error.setFixedHeight(CONTROL_HEIGHT * 2)
        layout.addRow(error)
        def clear_error():
            layout.setRowVisible(error, False)
            dialog.adjustSize()
        material.editTextChanged.connect(clear_error)
        def mode_changed():
            layout.setRowVisible(material, mode.currentData() == "material")
            note.setText({"all": "Replace destination blocks\nin the copied area.",
                          "air": "Fill air only.\nKeep existing blocks.",
                          "material": "Match a block ID, or an exact\nstate with properties."}[mode.currentData()])
            clear_error()
        mode.currentIndexChanged.connect(mode_changed)
        mode_changed()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Use rule")
        def accept():
            try:
                rule = DestinationRule(mode.currentData(), material.currentText().strip())
            except ValueError:
                error.setText("Enter a block ID:\nminecraft:stone")
                layout.setRowVisible(error, True)
                dialog.adjustSize()
                material.setFocus()
                return
            self.set_rule(rule)
            self.changed.emit(rule)
            dialog.accept()
        buttons.accepted.connect(accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        dialog.exec()
        dialog.deleteLater()
