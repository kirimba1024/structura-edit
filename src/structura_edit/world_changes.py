from copy import copy
from uuid import uuid4

from .changes import StaleChangeError
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
        patch = self.entities if entities else self.patch
        updates = {}
        for delta in changes:
            before, after = (delta.after, delta.before) if reverse else (delta.before, delta.after)
            key = delta.key if entities else delta.position
            previous = updates[key] if key in updates else patch.get(key)
            baseline = previous[0] if previous is not None else before
            updates[key] = None if after == baseline else (baseline, after)
        return updates

    def apply(self, change):
        if (change.document_id, change.base_revision) != (self.document_id, self.revision):
            raise StaleChangeError("The world changed; create a fresh preview")
        if not change:
            return 0
        patch = self._updated(change.changes)
        entities = self._updated(change.entities, entities=True)
        size = len(self.patch) + len(self.entities)
        size += sum((value is not None) - (key in self.patch) for key, value in patch.items())
        size += sum((value is not None) - (key in self.entities) for key, value in entities.items())
        if size > MAX_PENDING_BLOCKS:
            raise ValueError(f"Pending world changes exceed {MAX_PENDING_BLOCKS:,} blocks; save before editing more")
        state_id = uuid4().hex
        self.history.append(change, self.state_id, state_id)
        _update(self.patch, patch)
        _update(self.entities, entities)
        self.state_id = state_id
        self.revision += 1
        return len(change)

    def step(self, *, undo):
        index = self.history.cursor - 1 if undo else self.history.cursor
        if not 0 <= index < len(self.history.entries):
            return None
        entry, change = self.history.get(index)
        patch = self._updated(change.changes, reverse=undo)
        entities = self._updated(change.entities, reverse=undo, entities=True)
        _update(self.patch, patch)
        _update(self.entities, entities)
        self.history.cursor += -1 if undo else 1
        self.state_id = entry.before if undo else entry.after
        self.revision += 1
        return change

    def fork(self):
        branch = copy(self)
        branch.patch = self.patch.copy()
        branch.entities = self.entities.copy()
        branch.history = History(self.history.cache_limit, persistent=False, cache_bytes=self.history.cache_bytes)
        return branch


def _update(patch, updates):
    for key, value in updates.items():
        if value is None:
            patch.pop(key, None)
        else:
            patch[key] = value
