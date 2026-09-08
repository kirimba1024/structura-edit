from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QPlainTextEdit, QVBoxLayout

from .appearance import GRID


def show_error(parent, message):
    dialog = QDialog(parent)
    dialog.setWindowTitle("Error details")
    dialog.resize(GRID * 192, GRID * 96)
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(GRID * 2, GRID * 2, GRID * 2, GRID * 2)
    layout.setSpacing(GRID)
    text = QPlainTextEdit(message)
    text.setReadOnly(True)
    text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
    layout.addWidget(text)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    copy = buttons.addButton("Copy error", QDialogButtonBox.ButtonRole.ActionRole)
    copy.clicked.connect(lambda: QApplication.clipboard().setText(message))
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    dialog.exec()
