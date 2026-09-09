import pytest

pytest.importorskip("PySide6.QtWidgets")
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QInputDialog, QLineEdit

from structura_edit.source_ui import SourceDialog, source_version_options
from structura_edit.source_loading import SourceVersionRequired


@pytest.mark.parametrize("name", ["house.nbt", "house.snbt", "house.schem", "house.schematic", "house.litematic", "house.mcstructure", "level.dat"])
def test_open_accepts_schematic_files_and_level_dat(qt_app, tmp_path, name):
    path = tmp_path / name
    path.touch()
    dialog = SourceDialog()
    try:
        dialog.selectFile(str(path))
        dialog.accept()
        assert dialog.result() == QDialog.DialogCode.Accepted
        assert dialog.path == str(path)
    finally:
        dialog.deleteLater()


@pytest.mark.parametrize("select_folder", [False, True])
def test_open_accepts_world_folder_or_current_world_directory(qt_app, tmp_path, select_folder):
    world = tmp_path / "My world"
    world.mkdir()
    (world / "level.dat").touch()
    dialog = SourceDialog()
    try:
        dialog.setDirectory(str(tmp_path if select_folder else world))
        if select_folder:
            dialog.findChild(QLineEdit, "fileNameEdit").setText(world.name)
        else:
            dialog.directoryEntered.emit(str(world))
        dialog.show()
        qt_app.processEvents()
        assert dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Open).isEnabled()
        dialog.accept()
        assert dialog.result() == QDialog.DialogCode.Accepted
        assert dialog.path == str(world if select_folder else world / "level.dat")
    finally:
        dialog.close()
        dialog.deleteLater()


def test_open_browses_regular_directories_without_accepting_them(qt_app, tmp_path):
    folder = tmp_path / "schematics"
    folder.mkdir()
    dialog = SourceDialog()
    try:
        dialog.setDirectory(str(tmp_path))
        dialog.findChild(QLineEdit, "fileNameEdit").setText(folder.name)
        dialog.accept()
        assert dialog.result() == QDialog.DialogCode.Rejected
        assert dialog.path is None
        assert dialog.directory().absolutePath() == str(folder)
    finally:
        dialog.deleteLater()


@pytest.mark.parametrize("cancel", [False, True])
def test_source_version_rejects_invalid_input_and_preserves_request_options(qt_app, cancel):
    checks = []
    def answer():
        dialog = QApplication.activeModalWidget()
        if not isinstance(dialog, QInputDialog):
            return
        timer.stop()
        button = dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok)
        for value in ("", "unknown", "-1", "2147483648"):
            dialog.setTextValue(value)
            checks.append(not button.isEnabled())
        dialog.setTextValue("3955")
        checks.append(button.isEnabled())
        dialog.reject() if cancel else button.click()
    timer = QTimer()
    timer.timeout.connect(answer)
    timer.start(10)
    request = SourceVersionRequired({"path": "old.schem", "region": None})
    try:
        result = source_version_options(None, request)
    finally:
        timer.stop()
    assert checks and all(checks)
    assert result == (None if cancel else {"path": "old.schem", "region": None, "source_data_version": 3955})
    assert request.options == {"path": "old.schem", "region": None}
