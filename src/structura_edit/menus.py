from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence

from .commands import COMMANDS, UI_COMMANDS
from .navigation import CONTROLS
from .panels import CommandSearch
from .action_state import history_action


descriptions = {
    "inspect": "Inspect the selection: block states, material counts, entities, inventories and NBT. For a region, open Block data or Entities and double-click an object for its details.",
    "select_tool": "Select blocks: click the first corner, then Shift-click the opposite corner. Tab switches between flying and the cursor. Esc clears the selection and returns to flying.",
    "take": "Move the selection: point to a destination, drag an axis, or enter X / Y / Z in Options. Place confirms; Esc cancels. The original is removed only after Place.",
    "duplicate": "Place a copy of the selection immediately. The original stays in place. Esc cancels.",
    "copy": "Store the selection in the clipboard. Use Paste later to choose where to place it.",
    "paste": "Choose where to place the clipboard. Place confirms; Esc cancels.",
    "repeat": "Build several copies in a row using a count and spacing. Preview before applying.",
    "materials": "Find a block to use in Fill, Replace or another selection action.",
    "entity_move": "Move only the selected entities by an exact X / Y / Z offset. Blocks stay in place.",
    "entity_duplicate": "Copy only the selected entities by an exact X / Y / Z offset.",
    "height": "Hide blocks above a chosen height, or show one horizontal layer. This only changes the view.",
    "refresh": "Reload the area around the camera from disk and keep your pending edits. Loading happens only when requested.",
    "open": "Open a schematic or Java world. Schematics are framed automatically; worlds load near the saved player or spawn.",
    "save": "Save your edits to the document. For a world, update only changed blocks and entities in freshly read chunks; conflicting external changes need review.",
    "save_as": "Save this schematic to another file. The current file stays unchanged.",
    "export": "Export the selected region to a separate file. This does not save changes to the current world.",
    "import": "Read another schematic into the placement tool. Choose its destination and use Place; Esc cancels.",
    "undo": "Undo the last applied edit as one step. Loading and viewing do not create edit steps.",
    "redo": "Reapply an undone edit. Making a new edit discards the later Redo branch.",
    "history": "View actions, edits and errors with timing and details. Select a row to read it; Restore this state changes the document only for an edit.",
    "all": "Select every cell in the loaded document, including empty space. Use Inspect to see its materials and entities.",
    "clear": "Clear block and entity selections. The world is unchanged.",
    "coordinates": "Set the two corners of a block selection using world coordinates. Both corner blocks are included.",
    "world_settings": "Choose how far and how high to load around the camera. Apply loads that area and remembers these settings; flying never starts loading.",
    "bounds": "Show the edge of the currently loaded data. Beyond it, use Load here or F5 to request another area.",
    "chunks": "Show 16 × 16 chunk columns through the loaded height. Use Section grid to also see their 16-block vertical divisions.",
    "sections": "Show the 16 × 16 × 16 sections inside chunk columns. This is a guide; it does not change the loaded world.",
    "fit": "Move the camera to see the complete loaded structure. No blocks move.",
    "goto": "Move the camera to exact world coordinates. Use F5 if the destination is outside the loaded area.",
    "connected": "Select touching blocks of the same material. Click a starting block; Esc clears the selection.",
    "planar": "Select a flat connected block face for Extrude or Frame. Click a face in the scene; Esc cancels the tool.",
    "paint": "Paint only existing selected blocks along a brush stroke. Choose a material and radius; release to commit, Esc to cancel the stroke.",
    "entity_all": "Select entities whose positions are inside the current block region, or all loaded entities when no region is selected.",
    "entity_rotate": "Rotate selected entities around their shared center. Blocks stay in place; Undo restores the complete operation.",
    "entity_delete": "Remove the selected entities. Review the operation before applying; Undo restores them.",
    "entities": "Show or hide entity models and markers. Hiding does not delete or save anything.",
    "map": "Expand the six-view map. Surface shows outer surfaces; Slices shows cuts through the camera. M or Esc returns to the scene.",
    "apply": "Apply the prepared edit as one Undo step. Save writes local edits to disk.",
    "discard": "Discard the current preview or placement. Applied edits are unchanged.",
    "close": "Open the exit menu. Save and exit, leave without saving, or Cancel to keep editing.",
}



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
        objects = bar.addMenu("&Objects")
        help_menu = bar.addMenu("&Help")
        for menu in (file, edit, selection, view, objects, help_menu):
            menu.setToolTipsVisible(True)
        self.selection_menu = selection
        entries = (
            (file, "open", "Open…", QKeySequence.StandardKey.Open),
            (file, "save", "Save", QKeySequence.StandardKey.Save),
            (file, "save_as", "Save as…", QKeySequence.StandardKey.SaveAs),
            (file, "export", "Export selection…", None),
            (file, "import", "Import schematic…", "Ctrl+Shift+I"),
            (file, "backups", "Restore backup…", None),
            (file, "draft_save", "Save local draft", None),
            (file, "draft_recover", "Recover local draft…", None),
            (file, "close", "Exit…", QKeySequence.StandardKey.Close),
            (edit, "undo", "Undo", QKeySequence.StandardKey.Undo),
            (edit, "redo", "Redo", QKeySequence.StandardKey.Redo),
            (edit, "history", "History…", None),
            (edit, "revert", "Revert to opened…", None),
            (edit, "copy", "Copy", QKeySequence.StandardKey.Copy),
            (edit, "take", "Move selection…", QKeySequence.StandardKey.Cut),
            (edit, "paste", "Paste", QKeySequence.StandardKey.Paste),
            (edit, "duplicate", "Duplicate", "Ctrl+D"),
            (edit, "repeat", "Repeat selection…", None),
            (edit, "fragment_save", "Save selection to library…", None),
            (edit, "fragments", "Local fragments…", None),
            (edit, "apply", "Apply preview", None),
            (edit, "discard", "Discard preview", None),
            (edit, "recipe", "Python recipe…", None),
            (objects, "find_objects", "Find objects…", QKeySequence.StandardKey.Find),
            (objects, "inspect", "Inspect selection…", None),
            (objects, "entity_all", "Select entities in region", None),
            (objects, "entity_move", "Move entities…", None),
            (objects, "entity_duplicate", "Duplicate entities…", None),
            (objects, "entity_rotate", "Rotate entities…", None),
            (objects, "entity_delete", "Delete entities…", None),
            (selection, "all", "Select all", "Ctrl+A"),
            (selection, "select_tool", "Select blocks", None),
            (selection, "clear", "Clear selection", "Ctrl+Shift+A"),
            (selection, "connected", "Connected select", None),
            (selection, "planar", "Planar select", None),
            (selection, "paint", "Paint selected blocks…", None),
            (selection, "coordinates", "Coordinates…", None),
            (selection, "materials", "Materials…", None),
            (view, "fit", "Fit scene (F)", None),
            (view, "fly", "Focus camera (Shift+`)", None),
            (view, "map", "Map (M)", None),
            (view, "height", "Visible heights…", None),
            (view, "goto", "Go to coordinates…", None),
            (view, "refresh", "Load here", "F5"),
            (view, "world_settings", "World view distance…", None),
            (view, "entities", "Show entities", None),
            (view, "bounds", "Schematic / loaded-area outline", None),
            (view, "chunks", "Chunk columns", None),
            (view, "sections", "Section grid · 16 × 16 × 16", None),
            (view, "resources", "Minecraft resources…", None),
            (view, "changes", "Unsaved changes", None),
            (help_menu, "controls", "Controls and keys…", None),
            (help_menu, "about", "About Structura Edit", None),
        )
        for menu, name, label, shortcut in entries:
            action = QAction(label, window)
            action.triggered.connect(callbacks[name])
            if name in descriptions:
                action.setToolTip(descriptions[name])
            if name == "take":
                action.setIconText("Move")
            if shortcut is not None:
                action.setShortcut(QKeySequence(shortcut))
            if name in ("entities", "bounds", "chunks", "sections", "connected", "changes", "planar", "paint"):
                action.setCheckable(True)
                action.setChecked(name not in ("chunks", "sections", "connected", "changes", "planar", "paint"))
            menu.addAction(action)
            self.actions[name] = action
        selection.addSeparator()
        for name in UI_COMMANDS:
            command = COMMANDS[name]
            action = selection.addAction(name + "…", lambda checked=False, n=name: callbacks["operation"](n))
            action.setToolTip(command.description)
            self.actions[name] = action
        search = edit.addAction("Find command…", self.find_command)
        search.setShortcut(QKeySequence("Ctrl+Shift+P"))

    def show_controls(self):
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout

        from .appearance import GRID, PANEL_WIDTH

        dialog = QDialog(self.window)
        dialog.setWindowTitle("Controls and keys")
        dialog.setFixedWidth(PANEL_WIDTH)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(*([GRID * 2] * 4))
        layout.setSpacing(GRID)
        text = QLabel(CONTROLS)
        text.setWordWrap(True)
        layout.addWidget(text, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.clicked.connect(dialog.close)
        layout.addWidget(buttons)
        dialog.exec()

    def show_about(self):
        from PySide6.QtWidgets import QMessageBox

        import structura_edit

        box = QMessageBox(self.window)
        box.setWindowTitle("About Structura Edit")
        box.setText(f"Structura Edit {structura_edit.__version__}")
        box.setInformativeText("A schematic and world editor.\nEditing stays separate from the publishing pipeline.")
        box.exec()

    def sync(self, session, *, busy, selected, preview, preview_ready, world_active, placing=False, repeating=False,
             clipboard=False, object_count=0, single_block=False, connected=False, changes=False, stroke=False):
        ready = session is not None and not busy
        editable = ready and not session.readonly
        objects_ready = ready and not preview and not placing
        self.actions["connected"].setChecked(connected)
        self.actions["connected"].setEnabled(ready and not placing)
        self.actions["planar"].setEnabled(editable and not placing and not preview)
        self.actions["paint"].setEnabled(editable and selected and not placing and not preview)
        self.actions["changes"].setChecked(changes)
        self.actions["changes"].setEnabled(ready)
        self.actions["revert"].setEnabled(editable and session.can_undo and not preview and not placing)
        self.actions["backups"].setEnabled(world_active and not placing and not preview and not busy)
        self.actions["inspect"].setEnabled(objects_ready and (object_count > 0 or selected))
        for name in ("entity_all", "find_objects"):
            self.actions[name].setEnabled(objects_ready)
        for name in ("entity_move", "entity_duplicate", "entity_rotate", "entity_delete"):
            self.actions[name].setEnabled(objects_ready and editable and object_count > 0)
        self.selection_menu.setEnabled(session is not None)
        if session is None:
            reason = "Open a document"
        elif session.readonly:
            reason = session._document.capabilities.reason
        elif busy or placing:
            reason = "Finish the current operation"
        else:
            reason = "Select a region" if not selected else ""
        for name in (*UI_COMMANDS, "recipe"):
            self.actions[name].setEnabled(editable and selected and not placing)
            self.actions[name].setToolTip(reason or (COMMANDS[name].description if name in COMMANDS else "Run local Python"))
        self.actions["open"].setEnabled(not busy)
        self.actions["draft_save"].setEnabled(editable and not preview and not placing)
        self.actions["draft_recover"].setEnabled(not busy and not preview and not placing)
        self.actions["resources"].setEnabled(not busy and not placing)
        self.actions["entities"].setEnabled(not placing)
        self.actions["materials"].setEnabled(ready and not placing and not preview)
        self.actions["map"].setEnabled(session is not None)
        self.actions["fly"].setEnabled(session is not None)
        self.actions["refresh"].setEnabled(world_active and not placing and not preview)
        self.actions["world_settings"].setEnabled(world_active and not placing and not preview)
        self.actions["save"].setEnabled(editable and not preview and not placing)
        self.actions["save"].setText("Save world" if world_active else "Save")
        self.actions["save_as"].setEnabled(editable and not world_active and not preview and not placing)
        if world_active:
            self.actions["save"].setEnabled(editable and session.dirty and not preview and not placing)
        self.actions["export"].setEnabled(ready and selected and not preview and not placing)
        self.actions["fragment_save"].setEnabled(ready and selected and not preview and not placing)
        self.actions["fragments"].setEnabled(editable and not preview and not placing)
        self.actions["copy"].setEnabled(ready and selected and not preview and not placing)
        for name in ("take", "duplicate"):
            self.actions[name].setEnabled(editable and selected and not preview and not placing)
        self.actions["paste"].setEnabled(editable and clipboard and not preview and not placing)
        self.actions["repeat"].setEnabled(editable and selected and not preview and not placing)
        self.actions["import"].setEnabled(editable and not preview and not placing)
        for name in ("all", "clear", "coordinates", "select_tool"):
            self.actions[name].setEnabled(ready and not placing)
        self.actions["history"].setEnabled(session is not None)
        for name in ("undo", "redo"):
            state = history_action(session, name, busy=busy, preview=preview, placing=placing, stroke=stroke)
            self.actions[name].setText(state.label)
            self.actions[name].setEnabled(state.enabled)
        self.actions["apply"].setEnabled(editable and not stroke and (preview_ready or (placing and not repeating)))
        self.actions["discard"].setEnabled(preview or placing)

    def find_command(self):
        entries = [(action.text().replace("&", ""), action) for action in self.actions.values()]
        dialog = CommandSearch(self.window, entries)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.show()
