from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence

from .commands import COMMANDS, REGION_COMMANDS
from .panels import CommandSearch


class EditorMenus:
    def __init__(self, window, callbacks):
        self.window = window
        self.actions = {}
        bar = window.menuBar()
        bar.setNativeMenuBar(False)
        file = bar.addMenu("&File")
        edit = bar.addMenu("&Edit")
        selection = bar.addMenu("&Selection")
        view = bar.addMenu("&View")
        self.selection_menu = selection
        entries = (
            (file, "open", "Open…", QKeySequence.StandardKey.Open),
            (file, "world", "Open world…", None),
            (file, "save", "Save as…", QKeySequence.StandardKey.Save),
            (file, "export", "Export selection…", None),
            (file, "import", "Import schematic…", "Ctrl+Shift+I"),
            (file, "close", "Close", QKeySequence.StandardKey.Close),
            (edit, "undo", "Undo", QKeySequence.StandardKey.Undo),
            (edit, "redo", "Redo", QKeySequence.StandardKey.Redo),
            (edit, "history", "History…", None),
            (edit, "copy", "Copy", QKeySequence.StandardKey.Copy),
            (edit, "take", "Take", QKeySequence.StandardKey.Cut),
            (edit, "paste", "Paste", QKeySequence.StandardKey.Paste),
            (edit, "duplicate", "Duplicate", "Ctrl+D"),
            (edit, "apply", "Apply preview", None),
            (edit, "discard", "Discard preview", None),
            (edit, "recipe", "Python recipe…", None),
            (selection, "all", "Select all", None),
            (selection, "clear", "Clear selection", None),
            (selection, "coordinates", "Coordinates…", None),
            (selection, "materials", "Materials…", None),
            (view, "fit", "Fit scene (F)", None),
            (view, "fly", "Fly / freelook (Shift+`)", None),
            (view, "map", "Map (M)", None),
            (view, "goto", "Go to coordinates…", None),
            (view, "refresh", "Refresh world", "F5"),
            (view, "world_settings", "World radius and location…", None),
            (view, "entities", "Show entities", None),
            (view, "resources", "Minecraft resources…", None),
        )
        for menu, name, label, shortcut in entries:
            action = QAction(label, window)
            action.triggered.connect(callbacks[name])
            if shortcut is not None:
                action.setShortcut(QKeySequence(shortcut))
            if name == "entities":
                action.setCheckable(True)
                action.setChecked(True)
            menu.addAction(action)
            self.actions[name] = action
        selection.addSeparator()
        for name in REGION_COMMANDS:
            command = COMMANDS[name]
            action = selection.addAction(name + "…", lambda checked=False, n=name: callbacks["operation"](n))
            action.setToolTip(command.description)
            self.actions[name] = action
        search = edit.addAction("Find command…", self.find_command)
        search.setShortcut(QKeySequence("Ctrl+Shift+P"))

    def sync(self, session, *, busy, selected, preview, preview_ready, world_active, placing=False, clipboard=False):
        ready = session is not None and not busy
        editable = ready and not session.readonly
        self.selection_menu.setEnabled(session is not None)
        for name in (*REGION_COMMANDS, "recipe"):
            self.actions[name].setEnabled(editable and selected and not placing)
        self.actions["open"].setEnabled(not busy)
        self.actions["world"].setEnabled(not busy)
        self.actions["resources"].setEnabled(not busy and not placing)
        self.actions["entities"].setEnabled(not placing)
        self.actions["materials"].setEnabled(ready and not placing and not preview)
        self.actions["map"].setEnabled(session is not None)
        self.actions["fly"].setEnabled(session is not None)
        self.actions["refresh"].setEnabled(world_active and not placing and not preview)
        self.actions["world_settings"].setEnabled(world_active and not placing and not preview)
        self.actions["save"].setEnabled(editable and not preview and not placing)
        self.actions["save"].setText("Save world" if world_active else "Save as…")
        if world_active:
            self.actions["save"].setEnabled(editable and session.dirty and not preview and not placing)
        self.actions["export"].setEnabled(ready and selected and not preview and not placing)
        self.actions["copy"].setEnabled(ready and selected and not preview and not placing)
        for name in ("take", "duplicate"):
            self.actions[name].setEnabled(editable and selected and not preview and not placing)
        self.actions["paste"].setEnabled(editable and clipboard and not preview and not placing)
        self.actions["import"].setEnabled(editable and not preview and not placing)
        for name in ("all", "clear", "coordinates"):
            self.actions[name].setEnabled(session is not None and not placing)
        self.actions["undo"].setEnabled(editable and session.can_undo)
        self.actions["redo"].setEnabled(editable and session.can_redo)
        self.actions["history"].setEnabled(session is not None)
        for name in ("undo", "redo"):
            label = getattr(session.history, name + "_label") if session else ""
            self.actions[name].setText(name.title() + (" " + label if label else ""))
        self.actions["apply"].setEnabled(editable and (preview_ready or placing))
        self.actions["discard"].setEnabled(preview or placing)

    def find_command(self):
        entries = [(action.text().replace("&", ""), action) for action in self.actions.values()]
        dialog = CommandSearch(self.window, entries)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.show()
