from copy import copy
from uuid import uuid4

from .history import History
from .loading import MAX_PENDING_BLOCKS


class WorldChanges:
    def __init__(self, document_id, history):
        self.document_id = document_id
        self.history = history
        self.patch = {}
        self.revision = 0
        self.state_id = uuid4().hex

    def _updated(self, changes, *, reverse=False):
        patch = self.patch.copy()
        for delta in changes:
            before, after = (delta.after, delta.before) if reverse else (delta.before, delta.after)
            baseline = patch[delta.position][0] if delta.position in patch else before
            if after == baseline:
                patch.pop(delta.position, None)
            else:
                patch[delta.position] = baseline, after
        return patch

    def apply(self, change):
        if not change:
            return 0
        patch = self._updated(change.changes)
        if len(patch) > MAX_PENDING_BLOCKS:
            raise ValueError(f"Pending world changes exceed {MAX_PENDING_BLOCKS:,} blocks; save before editing more")
        state_id = uuid4().hex
        self.history.append(change, self.state_id, state_id)
        self.patch = patch
        self.state_id = state_id
        self.revision += 1
        return len(change)

    def step(self, *, undo):
        index = self.history.cursor - 1 if undo else self.history.cursor
        if not 0 <= index < len(self.history.entries):
            return False
        entry, change = self.history.get(index)
        self.patch = self._updated(change.changes, reverse=undo)
        self.history.cursor += -1 if undo else 1
        self.state_id = entry.before if undo else entry.after
        self.revision += 1
        return True

    def fork(self):
        branch = copy(self)
        branch.patch = self.patch.copy()
        branch.history = History(self.history.cache_limit, persistent=False)
        return branch
