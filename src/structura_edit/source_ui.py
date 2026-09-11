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
        self.demo_path = None

    def _received(self, session):
        if isinstance(session, SourceVersionRequired):
            options = source_version_options(self.parent(), session)
            if options is not None:
                self.tasks.submit("open", self._received, **options)
            else:
                self.message.emit("Open cancelled")
        else:
            self.opened(session)

    def confirm_discard(self, continuation=None):
        if not self.document.session or not self.document.session.dirty:
            return True
        answer = QMessageBox.question(self.parent(), "Unsaved changes", "Save changes before continuing?",
                                      QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                                      QMessageBox.StandardButton.Cancel)
        if answer == QMessageBox.StandardButton.Save:
            self.save_dialog(on_saved=continuation)
        return answer == QMessageBox.StandardButton.Discard

    def open_dialog(self):
        dialog = SourceDialog(self.parent())
        if dialog.exec():
            self.open_path(dialog.path)

    def open_demo(self):
        from importlib.resources import files

        self.demo_path = Path(str(files("structura_render").joinpath("data/examples/demo.nbt")))
        self.open_path(self.demo_path)

    def open_path(self, path, region=None, *, palette_index=0, source_data_version=None):
        if self.tasks.busy:
            return
        path = Path(path).expanduser()
        def proceed():
            self.open_path(path, region, palette_index=palette_index, source_data_version=source_data_version)
        if not self.confirm_discard(proceed):
            return
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
        if not self.document.session or self.tasks.busy or self.document.pending is not None or self.document.selected.current is None:
            return
        path, _ = QFileDialog.getSaveFileName(self.parent(), "Export selection", "selection.nbt",
                                             "Structure NBT (*.nbt);;Text NBT (*.snbt);;Sponge (*.schem)")
        if not path:
            return
        token = self.document.input_token
        session, selection = self.document.session.fork(), self.document.selection()
        def reviewed(losses):
            if token != self.document.input_token:
                return
            if losses:
                answer = QMessageBox.question(self.parent(), "Export details",
                                              "The export uses the selection's lower corner as its anchor.\n\n" + "\n".join(losses) + "\n\nExport with these changes?",
                                              QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                                              QMessageBox.StandardButton.Cancel)
                if answer != QMessageBox.StandardButton.Yes:
                    return
            self.tasks.submit("export", lambda result: self.message.emit(f"Exported {result}"),
                              session=session, selection=selection, path=path)
        self.tasks.submit("export_review", reviewed, session=session, selection=selection, path=path)

    def save_dialog(self, *, save_as=False, on_saved=None):
        if not self.document.session or self.tasks.busy or self.document.pending is not None or self.placement.active:
            self.message.emit("Finish the current operation before saving")
            return False
        if self.world.active:
            return self.save_path(self.document.session.path, on_saved=on_saved)
        target = self.document.session.save_target
        if target is not None and not save_as:
            return self.save_path(target, on_saved=on_saved)
        current = self.document.session.path or Path("structure.nbt")
        if current.suffix.lower() == ".schematic":
            current = current.with_suffix(".nbt")
        suffix = current.suffix.lower()
        proposal = current.with_suffix(suffix) if target is not None else current.with_name(f"{current.stem}-edited{suffix}")
        if self.demo_path is not None and self.document.session.path == self.demo_path:
            proposal = Path.home() / "Documents" / "structure.nbt"
        filters = "Sponge (*.schem)" if suffix == ".schem" else "Structure NBT (*.nbt);;Text NBT (*.snbt)"
        path, _ = QFileDialog.getSaveFileName(self.parent(), "Save edited schematic", str(proposal), filters)
        if path:
            return self.save_path(path, on_saved=on_saved)
        return False

    def save_path(self, path, *, on_saved=None):
        if self.document.session and not self.document.session.readonly and self.document.pending is None and not self.placement.active:
            def received(session):
                self.saved(session)
                if on_saved is not None:
                    on_saved()
            return self.edits.save(path, received)
        return False
