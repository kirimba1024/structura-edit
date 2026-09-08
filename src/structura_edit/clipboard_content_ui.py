from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QWidget

from .appearance import GRID
from .controls import CellCheckBox, CellLabel


class ClipboardContent(QWidget):
    changed = Signal()

    def __init__(self):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(GRID)
        self.blocks = CellCheckBox("Blocks")
        self.entities = CellCheckBox("Entities")
        self.blocks.setToolTip("Blocks, including chest contents and other block data")
        self.entities.setToolTip("Mobs, frames and their data · passengers travel together · players stay")
        self.counts = None
        for field in (self.blocks, self.entities):
            field.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            field.setChecked(True)
            field.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            field.setMinimumWidth(GRID * 64)
            field.toggled.connect(self.changed)
            layout.addWidget(field, 1)
        self.note = CellLabel("Block rules affect blocks only")
        layout.addWidget(self.note, 2)

    def set_clipboard(self, clipboard):
        counts = (clipboard.block_count, len(clipboard.entities), clipboard.excluded_players)
        if counts == self.counts:
            return
        self.counts = counts
        self.blocks.setText(f"Blocks · {self.counts[0]:,}")
        self.entities.setText(f"Entities · {self.counts[1]:,}")
        suffix = f" · {clipboard.excluded_players:,} players stay" if clipboard.excluded_players else ""
        self.note.setText("Block rules affect blocks only" + suffix)
        self.blocks.setAccessibleName(self.blocks.text())
        self.entities.setAccessibleName(self.entities.text())

    def set_values(self, blocks, entities):
        for field, value in ((self.blocks, blocks), (self.entities, entities)):
            field.blockSignals(True)
            field.setChecked(value)
            field.blockSignals(False)

    def values(self):
        return dict(include_blocks=self.blocks.isChecked(), include_entities=self.entities.isChecked())
