from pathlib import Path

from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFileDialog, QInputDialog, QLineEdit
from structura_core.formats import STRUCTURE_SUFFIXES

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
