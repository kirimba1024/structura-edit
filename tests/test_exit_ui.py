from types import SimpleNamespace

import pytest
from PySide6.QtCore import QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QFileDialog, QLabel, QMessageBox, QWidget

from structura_edit.editor_document import EditorDocument
from structura_edit.exit_ui import ExitController, ExitDialog
from structura_edit.source_ui import SourceController
from structura_edit.action_state import editor_capabilities


class ExitWindow(QWidget):
    def closeEvent(self, event):
        if self.exit.confirm_close():
            self.closed += 1
            event.accept()
        else:
            event.ignore()


@pytest.fixture
def exit_window(edit, qt_app):
    window = ExitWindow()
    window.closed = 0
    window.document = EditorDocument()
    window.document.load(edit)
    window.tasks = SimpleNamespace(busy=False, protected=False)
    window.placement = SimpleNamespace(active=False)
    window.repeat = SimpleNamespace(active=False)
    window.paint = SimpleNamespace(dragging=False)
    window.status = QLabel(window)
    window.navigation = SimpleNamespace(suspend=lambda: None)
    window.jobs = []
    def save(path, callback):
        window.jobs.append((path, callback))
        return True
    window.sources = SourceController(window, window.document, window.tasks, SimpleNamespace(save=save),
                                      SimpleNamespace(active=False), window.placement, opened=lambda _: None,
                                      saved=lambda _: None,
                                      capabilities=lambda: editor_capabilities(window.document.session, busy=window.tasks.busy,
                                        preview=window.document.pending, placing=window.placement.active,
                                        repeating=window.repeat.active, stroke=window.paint.dragging))
    window.exit = ExitController(window)
    yield window
    window.exit.approved = True
    window.tasks.protected = False
    window.close()


def choose(window, button):
    QTimer.singleShot(0, lambda: window.exit.dialog.button(button).click())


@pytest.mark.parametrize("dirty", [False, True])
def test_exit_cancel_and_escape_keep_document_open(exit_window, dirty):
    window = exit_window
    if dirty:
        window.document.session.apply(window.document.session.set_block((0, 0, 0), "minecraft:gold_block"))
    choose(window, QMessageBox.StandardButton.Cancel)
    window.exit.request()
    QTimer.singleShot(0, lambda: QTest.keyClick(window.exit.dialog, Qt.Key.Key_Escape))
    window.exit.request()
    assert window.closed == 0 and window.document.session.dirty == dirty
    assert not window.jobs and window.exit.dialog is None


@pytest.mark.parametrize("dirty", [False, True])
def test_exit_confirmation_closes_once_without_second_prompt(exit_window, dirty):
    window = exit_window
    if dirty:
        window.document.session.apply(window.document.session.set_block((0, 0, 0), "minecraft:gold_block"))
    choose(window, QMessageBox.StandardButton.Discard if dirty else QMessageBox.StandardButton.Ok)
    window.exit.request()
    assert window.closed == 1 and not window.jobs


def test_save_and_exit_waits_for_success(exit_window, tmp_path, monkeypatch):
    window = exit_window
    session = window.document.session
    session.apply(session.set_block((0, 0, 0), "minecraft:gold_block"))
    target = tmp_path / "saved.nbt"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(target), ""))
    choose(window, QMessageBox.StandardButton.Save)
    window.exit.request()
    assert window.closed == 0 and session.dirty
    path, callback = window.jobs.pop()
    session.save(path)
    callback(session)
    assert window.closed == 1 and not session.dirty and target.is_file()


def test_cancelled_save_path_keeps_editor_open(exit_window, monkeypatch):
    window = exit_window
    session = window.document.session
    session.apply(session.set_block((0, 0, 0), "minecraft:gold_block"))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: ("", ""))
    choose(window, QMessageBox.StandardButton.Save)
    window.exit.request()
    assert window.closed == 0 and session.dirty and not window.jobs


def test_pending_preview_is_preserved_when_native_close_is_cancelled(exit_window):
    from structura_edit.editor_document import EditPreview

    window = exit_window
    change = window.document.session.set_block((0, 0, 0), "minecraft:gold_block")
    window.document.show_preview(EditPreview(change, "paint"))
    choose(window, QMessageBox.StandardButton.Cancel)
    window.close()
    assert window.closed == 0 and window.document.pending is change


def test_save_and_exit_buttons_follow_background_work_and_preserve_safe_default(exit_window):
    window = exit_window
    window.document.session.apply(window.document.session.set_block((0, 0, 0), "minecraft:gold_block"))
    dialog = ExitDialog(window)
    try:
        assert dialog.save.isEnabled()
        assert dialog.defaultButton() is dialog.button(QMessageBox.StandardButton.Cancel)
        assert dialog.escapeButton() is dialog.button(QMessageBox.StandardButton.Cancel)
        window.tasks.busy = window.tasks.protected = True
        dialog.refresh()
        assert not dialog.save.isEnabled() and not dialog.leave.isEnabled()
        window.tasks.busy = window.tasks.protected = False
        dialog.refresh()
        assert dialog.save.isEnabled() and dialog.leave.isEnabled()
        window.placement.active = True
        dialog.refresh()
        assert not dialog.save.isEnabled() and "unfinished edit" in dialog.informativeText()
    finally:
        dialog.timer.stop()
        dialog.close()


def test_protected_write_cannot_be_interrupted_by_exit(exit_window):
    window = exit_window
    window.tasks.protected = True
    window.exit.request()
    window.close()
    assert window.closed == 0 and window.exit.dialog is None
    assert "finish before exiting" in window.status.text()
