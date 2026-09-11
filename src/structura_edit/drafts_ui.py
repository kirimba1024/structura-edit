from time import monotonic
from datetime import datetime

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QInputDialog, QMessageBox


class DraftController(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.last_attempt = monotonic()
        self.saved_key = None
        self.document_id = None
        self.latest = "No checkpoint yet · saves after 30 seconds when idle"

    def opened(self, session):
        if self.document_id != session._id:
            self.document_id = session._id
            self.saved_key = None
            self.latest = "No checkpoint yet · saves after 30 seconds when idle"

    def tick(self):
        window = self.window
        session = window.document.session
        if session is None or session.readonly or not session.dirty or window.tasks.busy:
            return
        if window.document.pending is not None or window.paint.dragging or window.placement.active or window.repeat.active:
            return
        if monotonic() - self.last_attempt >= 30 and self.saved_key != (session._id, session.revision):
            self.save()

    def save(self):
        window = self.window
        session = window.document.session
        if session is None or window.tasks.busy:
            return
        key = session._id, session.revision
        self.last_attempt = monotonic()
        def received(path):
            self.saved_key = key
            self.latest = f"Draft saved at {datetime.now():%H:%M:%S} · earlier Undo history is not included"
            window.document_status.setToolTip(self.latest + "\n" + str(path))
            window.status.setText("Draft saved locally")
        window.tasks.submit("draft_save", received, session=session.fork())

    def recover(self):
        window = self.window
        if window.tasks.busy:
            return
        def listed(rows):
            if not rows:
                window.status.setText("No local drafts yet")
                return
            labels = [f"{row['updated'][:19]} · {row['source'] or 'Untitled'}" for row in rows]
            choice, accepted = QInputDialog.getItem(window, "Recover local draft", "Checkpoint (earlier Undo history is unavailable):", labels, editable=False)
            if not accepted:
                return
            path = rows[labels.index(choice)]["path"]
            def proceed():
                window.tasks.submit("draft_restore", restored, path=path)
            if window.sources.confirm_discard(proceed):
                proceed()
        def restored(session):
            window._opened(session)
            window.world.reset_request()
            window.navigation.stop()
            self.latest = session.recovery_notice
            window.add_issues((session.recovery_notice, *getattr(session, "notices", ())))
            QMessageBox.information(window, "Draft recovered", "The local edits are restored. Earlier Undo history is unavailable.\nThe source has not been written.")
        window.tasks.submit("draft_list", listed)
