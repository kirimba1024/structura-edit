from amulet_nbt import StringTag, from_snbt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QLineEdit, QPlainTextEdit, QVBoxLayout

from .appearance import GRID
from .controls import CellLabel
from .nbt_values import SCALARS, parse_scalar, path_text, scalar_text


class NbtValueDialog(QDialog):
    def __init__(self, parent, path, value, *, readonly=False, validate=None):
        super().__init__(parent)
        self.setWindowTitle("View value" if readonly else "Edit value")
        self.resize(720, 280)
        self.original = self.value = value
        self.validate = validate
        self.readonly = readonly
        self.scalar = isinstance(value, SCALARS)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*([GRID * 2] * 4))
        layout.setSpacing(GRID)
        layout.addWidget(CellLabel(path_text(path)))
        layout.addWidget(QLabel(f"Stored type: {type(value).__name__.removesuffix('Tag')}"))
        payload = scalar_text(value) if self.scalar else value.to_snbt(indent=2)
        multiline = isinstance(value, StringTag) or not self.scalar
        self.editor = QPlainTextEdit(payload) if multiline else QLineEdit(payload)
        self.editor.setReadOnly(readonly)
        self.editor.setAccessibleName("Value")
        if isinstance(self.editor, QLineEdit):
            self.editor.setMaxLength(128)
        layout.addWidget(self.editor)
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setMinimumHeight(36)
        layout.addWidget(self.error)
        if not self.scalar:
            layout.addWidget(QLabel("Advanced NBT text. Keep the existing field types."))
            self.resize(720, 440)
        kinds = QDialogButtonBox.StandardButton
        self.buttons = QDialogButtonBox(kinds.Close if readonly else kinds.Ok | kinds.Cancel)
        if not readonly:
            self.buttons.button(kinds.Ok).setText("Keep change")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.editor.setFocus()
        if not multiline:
            self.editor.selectAll()

    def accept(self):
        if self.readonly:
            return
        try:
            text = self.editor.toPlainText() if isinstance(self.editor, QPlainTextEdit) else self.editor.text()
            original = scalar_text(self.original) if self.scalar else self.original.to_snbt(indent=2)
            value = self.original if text == original else parse_scalar(self.original, text) if self.scalar else from_snbt(text)
            if self.validate is not None:
                self.validate(value)
            self.value = value
        except Exception as error:
            self.error.setText(str(error))
            return
        super().accept()
