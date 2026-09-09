from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFileDialog, QInputDialog, QLineEdit, QMessageBox
from structura_core.formats import STRUCTURE_SUFFIXES

from .source_loading import SourceVersionRequired


STRUCTURE_FILTER = "Minecraft (" + " ".join("*" + suffix for suffix in STRUCTURE_SUFFIXES) + ")"


def source_version_options(parent, request):
    dialog = QInputDialog(parent)
    dialog.setWindowTitle("Source Minecraft version")
    dialog.setLabelText("This Sponge file has no DataVersion.\nEnter the source Java DataVersion (an integer):")
    dialog.setInputMode(QInputDialog.InputMode.TextInput)
    dialog.setOkButtonText("Continue")
    field = dialog.findChild(QLineEdit)
    field.setValidator(QIntValidator(0, 2**31 - 1, field))
    button = dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok)
    dialog.textValueChanged.connect(lambda _: button.setEnabled(field.hasAcceptableInput()))
    button.setEnabled(False)
    if not dialog.exec():
        return None
    return dict(request.options, source_data_version=field.validator().locale().toInt(dialog.textValue())[0])


class SourceDialog(QFileDialog):
    def __init__(self, parent=None):
        super().__init__(parent, "Open schematic or world")
        self.setOption(QFileDialog.Option.DontUseNativeDialog)
        self.setFileMode(QFileDialog.FileMode.ExistingFile)
        self.setNameFilters([STRUCTURE_FILTER[:-1] + " level.dat)", "All files (*)"])
        self.setLabelText(QFileDialog.DialogLabel.FileName, "File or world folder:")
        self.path = None
        self.directoryEntered.connect(self._select_world)
        self._select_world(self.directory().absolutePath())

    def _select_world(self, directory):
        path = Path(directory) / "level.dat"
        if path.is_file():
            self.selectFile(str(path))

    def accept(self):
        selected = self.selectedFiles()
        path = Path(selected[0] if selected else self.directory().absolutePath())
        if path.is_dir() and (path / "level.dat").is_file():
            self.path = str(path)
            QDialog.accept(self)
        else:
            super().accept()
            if self.result() == QDialog.DialogCode.Accepted:
                self.path = self.selectedFiles()[0]


class SourceController(QObject):
    opening = Signal()
    message = Signal(str)

    def __init__(self, parent, document, tasks, edits, world, placement, *, opened, saved):
        super().__init__(parent)
        self.document, self.tasks, self.edits = document, tasks, edits
        self.world, self.placement = world, placement
        self.opened, self.saved = opened, saved

    def _received(self, session):
        if isinstance(session, SourceVersionRequired):
            options = source_version_options(self.parent(), session)
            if options is not None:
                self.tasks.submit("open", self._received, **options)
            else:
                self.message.emit("Open cancelled")
        else:
            self.opened(session)

    def confirm_discard(self):
        if not self.document.session or not self.document.session.dirty:
            return True
        answer = QMessageBox.question(self.parent(), "Unsaved changes", "Discard unsaved changes?",
                                      QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                                      QMessageBox.StandardButton.Cancel)
        return answer == QMessageBox.StandardButton.Discard

    def open_dialog(self):
        dialog = SourceDialog(self.parent())
        if dialog.exec():
            self.open_path(dialog.path)

    def open_demo(self):
        from importlib.resources import files

        self.open_path(str(files("structura_render").joinpath("data/examples/demo.nbt")))

    def open_path(self, path, region=None, *, palette_index=0, source_data_version=None):
        if self.tasks.busy or not self.confirm_discard():
            return
        path = Path(path).expanduser()
        self.opening.emit()
        if path.is_dir() or path.name == "level.dat":
            self.world.open(path if path.is_dir() else path.parent)
            return
        self.tasks.submit("open", self._received, path=str(path), region=region, palette_index=palette_index,
                      source_data_version=source_data_version)

    def import_dialog(self):
        if not self.document.session or self.document.session.readonly or self.tasks.busy or self.placement.active:
            return
        path, _ = QFileDialog.getOpenFileName(self.parent(), "Import as placement", "", STRUCTURE_FILTER)
        if path:
            self.placement.start("import", path=path)

    def export_dialog(self):
        if not self.document.session or self.tasks.busy or self.document.pending is not None or self.document.selected.region is None:
            return
        path, _ = QFileDialog.getSaveFileName(self.parent(), "Export selection as Structure NBT", "selection.nbt",
                                             "Structure NBT (*.nbt);;Text NBT (*.snbt)")
        if path:
            self.tasks.submit("export", lambda result: self.message.emit(f"Exported {result}"),
                      session=self.document.session.fork(), selection=self.document.selection(), path=path)

    def save_dialog(self):
        if not self.document.session or self.tasks.busy or self.document.pending is not None:
            return
        if self.world.active:
            self.save_path(self.document.session.path)
            return
        current = self.document.session.path or Path("structure.nbt")
        if current.suffix.lower() == ".schematic":
            current = current.with_suffix(".nbt")
        proposal = str(current.with_name(f"{current.stem}-edited{current.suffix}"))
        filters = "Sponge (*.schem)" if current.suffix == ".schem" else "Structure NBT (*.nbt);;Text NBT (*.snbt)"
        path, _ = QFileDialog.getSaveFileName(self.parent(), "Save edited schematic", proposal, filters)
        if path:
            self.save_path(path)

    def save_path(self, path):
        if self.document.session and not self.document.session.readonly and self.document.pending is None and not self.placement.active:
            self.edits.save(path, self.saved)
