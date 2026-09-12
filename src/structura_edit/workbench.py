from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDockWidget, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
    QStackedWidget, QToolButton, QVBoxLayout, QWidget,
)

from .materials import MaterialsPanel
from .history_panel import HistoryPanel
from .minimap import MiniMap
from .panels import OperationPanel
from .selection_panel import SelectionPanel
from .scene_overlay import SceneOverlay
from .viewport import SceneView
from .appearance import CONTROL_HEIGHT, GRID, PANEL_WIDTH


class Workbench(QStackedWidget):
    open_requested = Signal()
    demo_requested = Signal()

    def __init__(self, *, cache_dir=None):
        super().__init__()
        welcome = QWidget()
        layout = QVBoxLayout(welcome)
        layout.addStretch()
        title = QLabel("Structura Edit")
        title.setObjectName("appTitle")
        layout.addWidget(title, alignment=Qt.AlignmentFlag.AlignCenter)
        buttons = QHBoxLayout()
        buttons.addStretch()
        for text, signal in (("Open", self.open_requested), ("Explore demo", self.demo_requested)):
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
        scene_page = QWidget()
        self.scene_layout = QVBoxLayout(scene_page)
        self.scene_layout.setContentsMargins(0, 0, 0, 0)
        self.scene_layout.setSpacing(0)
        self.scene_layout.addWidget(self.plotter, 1)
        self.addWidget(scene_page)
        self.plotter.resized.connect(self.minimap.reposition)


class RecipePanel(QWidget):
    preview_requested = Signal()
    apply_requested = Signal()
    discard_requested = Signal()

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        hint = QLabel("Local Python · full access to your files.\nCancel stops the worker; external side effects remain.\nUse edit and selection · Preview, then Apply")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.code = QPlainTextEdit('edit.apply(edit.fill(selection, "minecraft:stone"))')
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
        self.focus_target = window.plotter
        self.operation = OperationPanel()
        self.selection = SelectionPanel()
        self.materials = MaterialsPanel()
        self.recipe = RecipePanel()
        self.history = HistoryPanel()
        self.docks = {}
        for name, title in (("operation", "Selection action"), ("selection", "Selection bounds"),
                            ("materials", "Materials"), ("recipe", "Python recipe"), ("history", "History")):
            dock = QDockWidget(title, window.plotter)
            dock.setWidget(getattr(self, name))
            title_bar = QWidget(dock)
            title_bar.setAttribute(Qt.WidgetAttribute.WA_LayoutOnEntireRect)
            title_bar.setObjectName("panelTitle")
            row = QHBoxLayout(title_bar)
            row.setContentsMargins(GRID, 0, 0, 0)
            row.addWidget(QLabel(title), 1)
            close = QToolButton()
            close.setText("×")
            close.setAccessibleName("Close panel")
            close.setFixedSize(CONTROL_HEIGHT, CONTROL_HEIGHT)
            close.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            if name == "materials":
                close.clicked.connect(self.materials.dismissed)
            else:
                close.clicked.connect(lambda checked=False, key=name: self.close(key))
            row.addWidget(close)
            dock.setTitleBarWidget(title_bar)
            dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea)
            dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable)
            dock.setWindowFlags(Qt.WindowType.Widget)
            dock.setFixedWidth(PANEL_WIDTH)
            dock.hide()
            dock.visibilityChanged.connect(self.reposition)
            self.docks[name] = dock
        self.minimap = window.minimap
        self.focus_target.resized.connect(self.reposition)
        self.selection.dismissed.connect(lambda: self.close("selection"))

    def reposition(self, *args):
        if not hasattr(self, "minimap"):
            return
        visible = [dock for dock in self.docks.values() if not dock.isHidden()]
        width = min(PANEL_WIDTH, self.focus_target.width())
        for dock in visible:
            dock.setGeometry(self.focus_target.width() - width, 0, width, self.focus_target.height())
            dock.raise_()
        self.minimap.right_inset = width if visible else 0
        self.minimap.reposition()
        self.minimap.expanded_changed.emit(not self.minimap.collapsed)

    def close(self, name):
        self.docks[name].hide()
        self.focus_target.setFocus(Qt.FocusReason.OtherFocusReason)

    def show(self, name, *, focus=True):
        for key, dock in self.docks.items():
            dock.setVisible(key == name)
        self.reposition()
        target = self.docks[name].widget() if focus else self.focus_target
        target.setFocus(Qt.FocusReason.OtherFocusReason)

    def dismiss(self):
        for dock in self.docks.values():
            dock.hide()
