import pickle
import sqlite3
import zlib
from collections import OrderedDict
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4


_storage = None


@dataclass(frozen=True)
class HistoryEntry:
    key: str
    label: str
    cells: int
    before: str
    after: str


class History:
    def __init__(self, cache_limit=500_000, *, persistent=True):
        self.cache_limit = cache_limit
        self.persistent = persistent
        self.entries = []
        self.cursor = 0
        self.path = None
        self._cache = OrderedDict()
        self._cached_cells = 0

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
        while self.persistent and self._cached_cells > self.cache_limit:
            _, removed = self._cache.popitem(last=False)
            self._cached_cells -= len(removed)

    def append(self, change, before, after):
        entry = HistoryEntry(uuid4().hex, change.label, len(change), before, after)
        if self.persistent:
            self.prepare()
            body = zlib.compress(pickle.dumps(change, protocol=5), level=1)
            with closing(sqlite3.connect(self.path)) as db, db:
                db.execute("CREATE TABLE IF NOT EXISTS changes (id TEXT PRIMARY KEY, body BLOB NOT NULL)")
                db.execute("INSERT INTO changes VALUES (?, ?)", (entry.key, body))
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
            state.update(_cache=OrderedDict(), _cached_cells=0)
        return state
