from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QCheckBox, QLabel, QSizePolicy

from .appearance import CONTROL_HEIGHT


class CellLabel(QLabel):
    def __init__(self, text="", *, width=None):
        self._text = ""
        super().__init__()
        self.setProperty("cell", True)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setIndent(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored if width is None else QSizePolicy.Policy.Fixed,
                           QSizePolicy.Policy.Fixed)
        self.setFixedHeight(CONTROL_HEIGHT)
        if width is not None:
            self.setFixedWidth(width)
        self.setText(text)

    def text(self):
        return self._text

    def setText(self, text):
        self._text = text
        self.setAccessibleName(text)
        self.setToolTip(text)
        self._fit_text()

    def _fit_text(self):
        width = max(0, self.contentsRect().width() - self.margin() * 2)
        super().setText(self.fontMetrics().elidedText(self._text, Qt.TextElideMode.ElideRight, width))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_text()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange, QEvent.Type.ContentsRectChange):
            self._fit_text()


class CellCheckBox(QCheckBox):
    def hitButton(self, position):
        return self.rect().contains(position)
