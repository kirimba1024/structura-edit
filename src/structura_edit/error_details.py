from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QPlainTextEdit, QVBoxLayout

from .appearance import GRID


def error_summary(message):
    if "Editor code was updated" in message:
        return "Restart needed · see Issues"
    if "World changed at" in message:
        return "World changed · see Issues"
    if "absent chunks" in message:
        return "Chunk missing · see Issues"
    if "absent section" in message:
        return "Outside build height · see Issues"
    if "PermissionError" in message:
        return "No file access · see Issues"
    return "Action failed · see Issues"


def show_error(parent, message, *, issues=False):
    dialog = QDialog(parent)
    dialog.setWindowTitle("Document issues" if issues else "Error details")
    dialog.resize(GRID * 192, GRID * 96)
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(GRID * 2, GRID * 2, GRID * 2, GRID * 2)
    layout.setSpacing(GRID)
    text = QPlainTextEdit(message)
    text.setReadOnly(True)
    text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
    layout.addWidget(text)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    copy = buttons.addButton("Copy details" if issues else "Copy error", QDialogButtonBox.ButtonRole.ActionRole)
    copy.clicked.connect(lambda: QApplication.clipboard().setText(message))
    buttons.rejected.connect(dialog.reject)
    if issues:
        clear = buttons.addButton("Clear reviewed issues", QDialogButtonBox.ButtonRole.AcceptRole)
        clear.clicked.connect(dialog.accept)
    layout.addWidget(buttons)
    return dialog.exec()
