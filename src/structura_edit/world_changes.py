from copy import copy
from uuid import uuid4

from .history import History
from .loading import MAX_PENDING_BLOCKS


class WorldChanges:
    def __init__(self, document_id, history):
        self.document_id = document_id
        self.history = history
        self.patch = {}
        self.entities = {}
        self.revision = 0
        self.state_id = uuid4().hex

    def _updated(self, changes, *, reverse=False, entities=False):
        patch = (self.entities if entities else self.patch).copy()
        for delta in changes:
            before, after = (delta.after, delta.before) if reverse else (delta.before, delta.after)
            key = delta.key if entities else delta.position
            baseline = patch[key][0] if key in patch else before
            if after == baseline:
                patch.pop(key, None)
            else:
                patch[key] = baseline, after
        return patch

    def apply(self, change):
        if not change:
            return 0
        patch = self._updated(change.changes)
        entities = self._updated(change.entities, entities=True)
        if len(patch) + len(entities) > MAX_PENDING_BLOCKS:
            raise ValueError(f"Pending world changes exceed {MAX_PENDING_BLOCKS:,} blocks; save before editing more")
        state_id = uuid4().hex
        self.history.append(change, self.state_id, state_id)
        self.patch = patch
        self.entities = entities
        self.state_id = state_id
        self.revision += 1
        return len(change)

    def step(self, *, undo):
        index = self.history.cursor - 1 if undo else self.history.cursor
        if not 0 <= index < len(self.history.entries):
            return False
        entry, change = self.history.get(index)
        self.patch = self._updated(change.changes, reverse=undo)
        self.entities = self._updated(change.entities, reverse=undo, entities=True)
        self.history.cursor += -1 if undo else 1
        self.state_id = entry.before if undo else entry.after
        self.revision += 1
        return True

    def fork(self):
        branch = copy(self)
        branch.patch = self.patch.copy()
        branch.entities = self.entities.copy()
        branch.history = History(self.history.cache_limit, persistent=False)
        return branch
