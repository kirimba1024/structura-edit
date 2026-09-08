from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QSizePolicy, QWidget


class OverlayBar(QWidget):
    def __init__(self, plotter):
        super().__init__(plotter)
        self.setProperty("contextBar", True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_LayoutOnEntireRect)
        self.setAttribute(Qt.WidgetAttribute.WA_NoMousePropagation)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        plotter.installEventFilter(self)
        self.hide()

    def reposition(self):
        parent = self.parentWidget()
        self.setFixedWidth(parent.width())
        self.adjustSize()
        self.move(0, parent.height() - self.height())
        self.raise_()

    def eventFilter(self, watched, event):
        if watched is self.parentWidget() and event.type() == QEvent.Type.Resize:
            self.reposition()
        return super().eventFilter(watched, event)

    def event(self, event):
        result = super().event(event)
        if event.type() == QEvent.Type.LayoutRequest:
            self.reposition()
        return result
