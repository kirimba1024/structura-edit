import pickle
import sqlite3
import zlib
import sys
from collections import OrderedDict
from contextlib import closing, contextmanager
from dataclasses import dataclass, fields, is_dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4


_storage = None
DEFAULT_CACHE_BYTES = 64 * 1024 * 1024


def retained_bytes(value):
    seen = set()
    pending = [value]
    total = 0
    while pending:
        item = pending.pop()
        identity = id(item)
        if identity in seen:
            continue
        seen.add(identity)
        total += sys.getsizeof(item)
        if isinstance(item, dict):
            pending.extend(item.keys())
            pending.extend(item.values())
        elif isinstance(item, (tuple, list, set, frozenset)):
            pending.extend(item)
        elif is_dataclass(item):
            if hasattr(item, "__dict__"):
                total += sys.getsizeof(item.__dict__)
            pending.extend(getattr(item, field.name) for field in fields(item))
    return total


@dataclass(frozen=True)
class HistoryEntry:
    key: str
    label: str
    cells: int
    before: str
    after: str


class History:
    def __init__(self, cache_limit=500_000, *, persistent=True, cache_bytes=DEFAULT_CACHE_BYTES):
        if isinstance(cache_bytes, bool) or not isinstance(cache_bytes, int) or cache_bytes <= 0:
            raise ValueError("History byte limit must be a positive integer")
        self.cache_limit = cache_limit
        self.cache_bytes = cache_bytes
        self.persistent = persistent
        self.entries = []
        self.cursor = 0
        self.path = None
        self._cache = OrderedDict()
        self._cached_cells = 0
        self._cache_sizes = {}
        self._cached_bytes = 0
        self._pending_prune = []
        self._defer_pruning = False

    @contextmanager
    def defer_pruning(self):
        previous = self._defer_pruning
        self._defer_pruning = True
        try:
            yield
        finally:
            self._defer_pruning = previous

    def prune(self):
        if self.persistent and self._pending_prune:
            with closing(sqlite3.connect(self.path)) as db, db:
                db.executemany('DELETE FROM changes WHERE id=?', ((key,) for key in self._pending_prune))
        self._pending_prune.clear()

    def _forget(self, key):
        removed = self._cache.pop(key, None)
        if removed is not None:
            self._cached_cells -= len(removed)
            self._cached_bytes -= self._cache_sizes.pop(key)

    def prepare(self):
        global _storage
        if self.persistent and self.path is None:
            if _storage is None:
                _storage = TemporaryDirectory(prefix="structura-history-")
            self.path = str(Path(_storage.name) / f"{uuid4().hex}.sqlite")

    def _remember(self, entry, change):
        if entry.key in self._cache:
            self._cache.move_to_end(entry.key)
            return
        self._cache[entry.key] = change
        self._cached_cells += len(change)
        self._cache_sizes[entry.key] = retained_bytes(change)
        self._cached_bytes += self._cache_sizes[entry.key]
        while self.persistent and (self._cached_cells > self.cache_limit or self._cached_bytes > self.cache_bytes):
            self._forget(next(iter(self._cache)))

    def append(self, change, before, after):
        entry = HistoryEntry(uuid4().hex, change.label, len(change), before, after)
        discarded = self.entries[self.cursor:]
        pruned = [item.key for item in discarded]
        if self.persistent:
            self.prepare()
            body = zlib.compress(pickle.dumps(change, protocol=5), level=1)
            with closing(sqlite3.connect(self.path)) as db, db:
                db.execute("CREATE TABLE IF NOT EXISTS changes (id TEXT PRIMARY KEY, body BLOB NOT NULL)")
                db.execute("INSERT INTO changes VALUES (?, ?)", (entry.key, body))
                if not self._defer_pruning:
                    db.executemany("DELETE FROM changes WHERE id=?", ((key,) for key in (*self._pending_prune, *pruned)))
        if self._defer_pruning:
            self._pending_prune.extend(pruned)
        else:
            self._pending_prune.clear()
        for item in discarded:
            self._forget(item.key)
        del self.entries[self.cursor:]
        self.entries.append(entry)
        self.cursor += 1
        self._remember(entry, change)

    def get(self, index):
        entry = self.entries[index]
        change = self._cache.get(entry.key)
        if change is None:
            with closing(sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)) as db:
                row = db.execute("SELECT body FROM changes WHERE id=?", (entry.key,)).fetchone()
            if row is None:
                raise OSError("History entry is missing; the document has not changed")
            change = pickle.loads(zlib.decompress(row[0]))
        self._remember(entry, change)
        return entry, change

    @property
    def undo_label(self):
        return self.entries[self.cursor - 1].label if self.cursor else ""

    @property
    def redo_label(self):
        return self.entries[self.cursor].label if self.cursor < len(self.entries) else ""

    def __getstate__(self):
        state = self.__dict__.copy()
        if self.persistent:
            state.update(_cache=OrderedDict(), _cached_cells=0, _cache_sizes={}, _cached_bytes=0)
        return state
