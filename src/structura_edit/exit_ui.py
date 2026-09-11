from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QMessageBox


def unfinished_edit(window):
    return (window.document.pending is not None or window.placement.active
            or window.repeat.active or window.paint.dragging)


class ExitDialog(QMessageBox):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setWindowTitle("Exit Structura")
        self.setTextFormat(Qt.TextFormat.PlainText)
        session = window.document.session
        dirty = session is not None and session.dirty
        unfinished = unfinished_edit(window)
        self.setText("Save changes before exiting?" if dirty else "Exit Structura?")
        buttons = self.StandardButton.Cancel
        buttons |= self.StandardButton.Discard if dirty or unfinished else self.StandardButton.Ok
        if dirty:
            buttons |= self.StandardButton.Save
        self.setStandardButtons(buttons)
        self.setDefaultButton(self.StandardButton.Cancel)
        self.setEscapeButton(self.StandardButton.Cancel)
        self.save = self.button(self.StandardButton.Save)
        if self.save is not None:
            self.save.setText("Save && Exit")
        self.leave = self.button(self.StandardButton.Discard) or self.button(self.StandardButton.Ok)
        self.leave.setText("Exit Without Saving" if dirty else "Discard Preview && Exit" if unfinished else "Exit")
        self.refresh()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(100)

    def refresh(self):
        window = self.window
        session = window.document.session
        unfinished = unfinished_edit(window)
        if window.tasks.protected:
            reason = "Wait for the current operation to finish."
        elif unfinished:
            reason = "An unfinished edit has not been applied. Cancel to finish or discard it before saving."
        elif session is not None and session.readonly:
            reason = "This document is read-only."
        elif window.tasks.busy:
            reason = "Wait for the current operation to finish before saving."
        else:
            reason = ""
        self.setInformativeText(reason or ("Your changes have not been saved." if session is not None and session.dirty
                                          else "All changes are saved." if session is not None else ""))
        if self.save is not None:
            self.save.setEnabled(not reason)
        self.leave.setEnabled(not window.tasks.protected)


class ExitController:
    def __init__(self, window):
        self.window = window
        self.dialog = None
        self.approved = False

    def request(self):
        if self.confirm_close(always=True):
            self.approved = True
            try:
                self.window.close()
            finally:
                self.approved = False

    def confirm_close(self, *, always=False):
        window = self.window
        if window.tasks.protected:
            window.status.setText("Wait for the current operation to finish before exiting")
            return False
        if self.approved:
            return True
        if self.dialog is not None:
            return False
        session = window.document.session
        if not always and (session is None or not session.dirty) and not unfinished_edit(window):
            return True
        window.navigation.suspend()
        dialog = self.dialog = ExitDialog(window)
        try:
            answer = dialog.exec()
        finally:
            dialog.timer.stop()
            self.dialog = None
            dialog.deleteLater()
        if answer == QMessageBox.StandardButton.Save:
            window.sources.save_dialog(on_saved=window.close)
        return answer in (QMessageBox.StandardButton.Discard, QMessageBox.StandardButton.Ok)
