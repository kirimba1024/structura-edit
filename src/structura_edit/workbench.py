from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDockWidget, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
    QStackedWidget, QVBoxLayout, QWidget,
)

from .materials import MaterialsPanel
from .history_panel import HistoryPanel
from .minimap import MiniMap
from .panels import OperationPanel
from .selection_panel import SelectionPanel
from .scene_overlay import SceneOverlay
from .viewport import SceneView


class Workbench(QStackedWidget):
    open_requested = Signal()
    world_requested = Signal()
    demo_requested = Signal()

    def __init__(self, *, cache_dir=None):
        super().__init__()
        welcome = QWidget()
        layout = QVBoxLayout(welcome)
        layout.addStretch()
        title = QLabel("Structura Edit")
        title.setFont(QFont(title.font().family(), 24))
        layout.addWidget(title, alignment=Qt.AlignmentFlag.AlignCenter)
        buttons = QHBoxLayout()
        buttons.addStretch()
        for text, signal in (("Open schematic", self.open_requested), ("Open world", self.world_requested),
                             ("Explore demo", self.demo_requested)):
            button = QPushButton(text)
            button.clicked.connect(signal)
            buttons.addWidget(button)
        buttons.addStretch()
        layout.addLayout(buttons)
        layout.addStretch()
        self.addWidget(welcome)
        self.plotter = SceneView(self)
        self.overlay = SceneOverlay(self.plotter)
        self.minimap = MiniMap(self.plotter, cache_dir=cache_dir)
        self.addWidget(self.plotter)
        self.plotter.resized.connect(self.minimap.reposition)


class RecipePanel(QWidget):
    preview_requested = Signal()
    apply_requested = Signal()
    discard_requested = Signal()

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        hint = QLabel("Local Python · edit and selection are available · Preview, then Apply")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.code = QPlainTextEdit('edit.apply(edit.fill(selection, "minecraft:stone"))')
        self.code.setFont(QFont("Menlo", 12))
        self.setFocusProxy(self.code)
        layout.addWidget(self.code)
        self.preview = QPushButton("Preview recipe")
        self.preview.clicked.connect(self.preview_requested)
        self.apply = QPushButton("Apply")
        self.discard = QPushButton("Discard")
        self.apply.clicked.connect(self.apply_requested)
        self.discard.clicked.connect(self.discard_requested)
        actions = QHBoxLayout()
        for button in (self.preview, self.apply, self.discard):
            actions.addWidget(button)
        layout.addLayout(actions)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setMaximumHeight(100)
        layout.addWidget(self.output)


class EditorPanels:
    def __init__(self, window):
        self.operation = OperationPanel()
        self.selection = SelectionPanel()
        self.materials = MaterialsPanel()
        self.recipe = RecipePanel()
        self.history = HistoryPanel()
        self.docks = {}
        for name, title in (("operation", "Selection action"), ("selection", "Selection coordinates"),
                            ("materials", "Selection materials"), ("recipe", "Python recipe"), ("history", "History")):
            dock = QDockWidget(title, window)
            dock.setWidget(getattr(self, name))
            dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea)
            dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable)
            window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
            dock.setMinimumWidth(280)
            dock.hide()
            self.docks[name] = dock

    def show(self, name):
        for key, dock in self.docks.items():
            dock.setVisible(key == name)
        self.docks[name].widget().setFocus(Qt.FocusReason.OtherFocusReason)

    def dismiss(self):
        for dock in self.docks.values():
            dock.hide()
