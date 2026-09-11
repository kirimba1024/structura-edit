from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QGridLayout, QSizePolicy, QWidget

from .appearance import GRID
from .controls import CellCheckBox, MessageLabel


class ClipboardContent(QWidget):
    changed = Signal()

    def __init__(self):
        super().__init__()
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(GRID)
        self.blocks = CellCheckBox("Blocks")
        self.entities = CellCheckBox("Entities")
        self.blocks.setToolTip("Blocks, including chest contents and other block data")
        self.entities.setToolTip("Mobs, frames and their data · passengers travel together · players stay")
        self.counts = None
        self.filtered = False
        for column, field in enumerate((self.blocks, self.entities)):
            field.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            field.setChecked(True)
            field.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            field.setMinimumWidth(GRID * 64)
            field.toggled.connect(self.changed)
            field.toggled.connect(self.update_note)
            layout.addWidget(field, 0, column)
            layout.setColumnStretch(column, 1)
        self.note = MessageLabel()
        layout.addWidget(self.note, 1, 0, 1, 2)
        self.note.hide()

    def set_clipboard(self, clipboard):
        counts = (clipboard.block_count, len(clipboard.entities), clipboard.excluded_players)
        if counts == self.counts:
            return
        self.counts = counts
        self.blocks.setText(f"Blocks · {self.counts[0]:,}")
        self.entities.setText(f"Entities · {self.counts[1]:,}")
        self.update_note()
        self.blocks.setAccessibleName(self.blocks.text())
        self.entities.setAccessibleName(self.entities.text())

    def set_values(self, blocks, entities):
        for field, value in ((self.blocks, blocks), (self.entities, entities)):
            field.blockSignals(True)
            field.setChecked(value)
            field.blockSignals(False)
        self.update_note()

    def set_rule(self, rule):
        self.filtered = rule.mode != "all"
        self.update_note()

    def update_note(self):
        if self.counts is None:
            return
        messages = []
        if self.filtered and self.entities.isChecked() and self.counts[1]:
            messages.append("Entities will still be pasted.")
        if self.counts[2]:
            messages.append(f"{self.counts[2]:,} players excluded from this copy.")
        self.note.setText(" ".join(messages))
        self.note.setVisible(bool(messages))

    def values(self):
        return dict(include_blocks=self.blocks.isChecked(), include_entities=self.entities.isChecked())
