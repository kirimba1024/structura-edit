from .commands import PARAMETERS


class MaterialController:
    def __init__(self, panels, navigation, *, available, show_operation):
        self.panels = panels
        self.navigation = navigation
        self.available = available
        self.show_operation = show_operation
        self.field = "target"
        self.mode = "Fill"
        self.return_to_operation = False
        panels.materials.chosen.connect(self.choose)
        panels.materials.dismissed.connect(self.dismiss)
        panels.operation.material_requested.connect(self.show)

    def show(self, field=None):
        if not self.available():
            return
        self.field = field or "target"
        self.mode = self.panels.operation.current if field else "Fill"
        self.return_to_operation = self.panels.docks["operation"].isVisible()
        self.navigation.stop()
        materials = self.panels.materials
        materials.search.clear()
        materials.reload()
        materials.use.setText(f"Use for {PARAMETERS[self.field].label}")
        self.panels.show("materials")

    def dismiss(self):
        self.panels.docks["materials"].hide()
        if self.return_to_operation:
            self.panels.show("operation")
            self.panels.operation.fields[self.field].setFocus()
        else:
            self.navigation.view.setFocus()

    def choose(self, state):
        if not self.available():
            return
        self.dismiss()
        self.show_operation(self.mode)
        field = self.panels.operation.fields[self.field]
        field.setText(state)
        field.setCursorPosition(0)
        if field.isVisible() and field.isEnabled():
            field.setFocus()
        self.remember(state)

    def remember(self, state):
        self.panels.materials.remember(state)
        self.panels.operation.set_materials(self.panels.materials.states)

    def set_counts(self, counts):
        self.panels.materials.set_counts(counts)
        self.panels.operation.set_materials(self.panels.materials.states)
