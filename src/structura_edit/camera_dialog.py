from PySide6.QtWidgets import QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout


def go_to_coordinates(parent, position, origin, move):
    dialog = QDialog(parent)
    dialog.setWindowTitle("Camera coordinates")
    layout = QFormLayout(dialog)
    fields = []
    for axis, value, offset in zip("XYZ", position, origin):
        field = QDoubleSpinBox()
        field.setRange(-30_000_000, 30_000_000)
        field.setValue(value + offset)
        layout.addRow(axis, field)
        fields.append(field)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addRow(buttons)
    if dialog.exec() == QDialog.DialogCode.Accepted:
        move(tuple(field.value() - offset for field, offset in zip(fields, origin)))
