from dataclasses import dataclass

from .changes import StaleChangeError
from .selection import RegionSelection


@dataclass(frozen=True)
class EditPreview:
    change: object
    kind: str = "operation"
    plan: object = None
    selection_after: object = None
    output: object = None
    material: object = None


@dataclass(frozen=True)
class DocumentUpdate:
    previous: object
    session: object

    @property
    def resized(self):
        return self.previous is None or (self.previous.size, self.previous.origin) != (self.session.size, self.session.origin)


class EditorDocument:
    def __init__(self):
        self._session = None
        self._preview = None
        self._epoch = 0
        self._input_revision = 0
        self.selected = RegionSelection()

    @property
    def session(self):
        return self._session

    @property
    def preview(self):
        return self._preview

    @property
    def pending(self):
        return self._preview.change if self._preview is not None else None

    @property
    def session_token(self):
        identity = (self.session._id, self.session.revision) if self.session is not None else None
        return self._epoch, identity

    @property
    def selection_token(self):
        return self.session_token, self.selected.region, self.selected.cells

    @property
    def input_token(self):
        return self.selection_token, self._input_revision

    def selection(self):
        if self.selected.current is None:
            raise ValueError("Click a block to select it; Shift+click another block to extend the region")
        return self.selected.current

    def load(self, session):
        self._session = session
        self._epoch += 1
        self.selected.reset(session.size if session is not None else (1, 1, 1))
        self.invalidate()

    def replace(self, session):
        if self.session is None or session._id != self.session._id or session.revision < self.session.revision:
            raise StaleChangeError("The document changed; the task result no longer applies")
        update = DocumentUpdate(self.session, session)
        self._session = session
        self._epoch += 1
        self.invalidate()
        if update.resized:
            self.selected.reset(session.size)
        return update

    def invalidate(self):
        had_preview = self._preview is not None
        self._preview = None
        self._input_revision += 1
        return had_preview

    def show_preview(self, preview, *, token=None):
        if self.session is None or (token is not None and token != self.input_token):
            return False
        self.session._check_change(preview.change)
        self._preview = preview
        return True
