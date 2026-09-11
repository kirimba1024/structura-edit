from dataclasses import dataclass
from sys import getsizeof
from typing import Optional

import numpy as np

from .picking import EMPTY
from .cell_set import CellSet


PAGE_SIZE = 64
MAX_INDEX_BYTES = 64 * 1024**2
MATCH_CHUNK = 4096
SEARCH_WORK_BYTES = 128 * 1024
RESULT_ROW_BYTES = 512


def search_revision(session):
    return session._id, session._state_id, session.revision, session.origin, session.size, getattr(session, "dimension", None)


@dataclass(frozen=True)
class ObjectMatch:
    kind: str
    identity: str
    position: tuple
    key: Optional[str] = None
    has_data: bool = False

    @property
    def name(self):
        return self.identity.split("[", 1)[0].split(":", 1)[-1].replace("_", " ").title()


@dataclass(frozen=True)
class ObjectPage:
    rows: tuple
    total: int
    offset: int


class BlockIndex:
    def __init__(self, session, budget=MAX_INDEX_BYTES):
        source = session._document.source
        capacity = len(source.present) + len(session._cells)
        self.budget = budget
        self.reserved_bytes = capacity * 18 + ((capacity + MATCH_CHUNK - 1) // MATCH_CHUNK + 1) * 8 + SEARCH_WORK_BYTES
        codes = {}
        for state in session._states:
            if state not in codes:
                codes[state] = len(codes)
                self.reserved_bytes += getsizeof(state) + 160
                self._check_budget()
        for cell in session._cells.values():
            if cell is not None and cell.state not in codes:
                codes[cell.state] = len(codes)
                self.reserved_bytes += getsizeof(cell.state) + 160
                self._check_budget()
        self._check_budget()
        self.states = tuple(codes)
        self.positions = np.empty((capacity, 3), dtype=np.int32)
        self.codes = np.empty(capacity, dtype=np.int32)
        self.has_data = np.empty(capacity, dtype=bool)
        self.query = self.mask = self.cumulative = None
        count = 0
        for position, index in source.present.items():
            if position not in session._cells and session._states[index].split("[", 1)[0] not in EMPTY:
                self.positions[count] = position
                self.codes[count] = codes[session._states[index]]
                self.has_data[count] = position in source.block_nbt
                count += 1
        for position, cell in session._cells.items():
            if cell is not None and cell.state.split("[", 1)[0] not in EMPTY:
                self.positions[count] = position
                self.codes[count] = codes[cell.state]
                self.has_data[count] = cell.keep_nbt
                count += 1
        self.positions, self.codes, self.has_data = self.positions[:count], self.codes[:count], self.has_data[:count]

    def _check_budget(self):
        if self.reserved_bytes > self.budget:
            raise ValueError("Object search exceeds 64 MiB; reduce the loaded area or search Entities only")

    def matches(self, words, kind, selection):
        query = tuple(words), kind, selection
        if self.query == query:
            return int(self.cumulative[-1])
        self.query = self.mask = self.cumulative = None
        states = np.fromiter((matches_text(state, words) for state in self.states), dtype=bool, count=len(self.states))
        count = len(self.codes)
        mask = np.empty(count, dtype=bool)
        cumulative = np.zeros((count + MATCH_CHUNK - 1) // MATCH_CHUNK + 1, dtype=np.int64)
        for chunk, start in enumerate(range(0, count, MATCH_CHUNK)):
            end = min(count, start + MATCH_CHUNK)
            part = mask[start:end]
            part[:] = states[self.codes[start:end]]
            if kind == "data":
                part &= self.has_data[start:end]
            if selection is not None:
                for axis in range(3):
                    part &= self.positions[start:end, axis] >= selection.lower[axis]
                    part &= self.positions[start:end, axis] < selection.upper[axis]
            if isinstance(selection, CellSet):
                for index in np.flatnonzero(part):
                    part[index] = tuple(map(int, self.positions[start + index])) in selection
            cumulative[chunk + 1] = cumulative[chunk] + np.count_nonzero(part)
        self.query, self.mask, self.cumulative = query, mask, cumulative
        return int(cumulative[-1])

    def page_indices(self, offset, limit):
        total = int(self.cumulative[-1])
        if offset >= total or limit <= 0:
            return
        chunk = int(np.searchsorted(self.cumulative, offset, side="right")) - 1
        remaining = min(limit, total - offset)
        while remaining:
            start = chunk * MATCH_CHUNK
            skip = max(0, offset - int(self.cumulative[chunk]))
            indices = np.flatnonzero(self.mask[start:start + MATCH_CHUNK])[skip:skip + remaining]
            yield from (start + int(index) for index in indices)
            remaining -= len(indices)
            chunk += 1

    def row(self, index):
        return ObjectMatch("block", self.states[self.codes[index]], tuple(map(int, self.positions[index])),
                           has_data=bool(self.has_data[index]))


def matches_text(identity, words):
    text = identity.casefold().replace("_", " ")
    return all(word in text for word in words)


class ObjectSearch:
    def __init__(self):
        self.reset()

    def reset(self):
        self.revision = self.blocks = self.entities = None
        self.entity_bytes = 0

    def find(self, session, text="", *, kind="all", selection=None, offset=0, limit=PAGE_SIZE):
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= PAGE_SIZE:
            raise ValueError(f"Use a non-negative offset and a page size from 1 to {PAGE_SIZE}")
        entities, total = self._matches(session, text, kind, selection)
        rows = list(entities[offset:offset + limit])
        start = max(0, offset - len(entities))
        if total:
            rows.extend(self.blocks.row(index) for index in self.blocks.page_indices(start, limit - len(rows)))
        return ObjectPage(tuple(rows), len(entities) + total, offset)

    def collect(self, session, text="", *, kind="all", selection=None, limit=10_000):
        if type(limit) is not int or limit <= 0:
            raise ValueError("Use a positive object limit")
        entities, total = self._matches(session, text, kind, selection)
        if len(entities) + total > limit:
            raise ValueError(f"More than {limit:,} objects match; narrow the search or selection")
        used = self.entity_bytes + (self.blocks.reserved_bytes if self.blocks is not None else 0)
        if used + total * RESULT_ROW_BYTES > MAX_INDEX_BYTES:
            raise ValueError("Object search results exceed 64 MiB; narrow the search or selection")
        blocks = (self.blocks.row(index) for index in self.blocks.page_indices(0, total)) if total else ()
        return (*entities, *blocks)

    def _matches(self, session, text, kind, selection):
        if kind not in ("all", "entities", "blocks", "data"):
            raise ValueError("Search type must be all, entities, blocks or data")
        if not isinstance(text, str) or len(text) > 256:
            raise ValueError("Search text must contain at most 256 characters")
        if selection is not None:
            session._check_selection(selection)
        revision = search_revision(session)
        if self.revision != revision:
            self.revision, self.blocks, self.entities = revision, None, None
            self.entity_bytes = 0
        words = text.casefold().replace("_", " ").split()
        entities, total = [], 0
        if kind in ("all", "entities"):
            if self.entities is None:
                self.blocks = None
                self.entities = tuple(entity_matches(session))
                self.entity_bytes = sum(entity_bytes(row) for row in self.entities)
            entities = [row for row in self.entities if matches_text(row.identity, words)
                        and (selection is None or row.position in selection)]
        if kind != "entities":
            if self.blocks is None:
                self.blocks = BlockIndex(session, MAX_INDEX_BYTES - self.entity_bytes)
            total = self.blocks.matches(words, kind, selection)
        return entities, total


def entity_bytes(row):
    return sum(map(getsizeof, (row, row.__dict__, row.position, *row.position, row.identity, row.key))) + 32


def entity_matches(session):
    used = 0
    for key, data in session._entities.items():
        record = data.unpack()
        identity = str(record["nbt"].get("id", "entity"))
        row = ObjectMatch("entity", identity, tuple(float(value) for value in record["pos"]), key, True)
        used += entity_bytes(row)
        if used > MAX_INDEX_BYTES:
            raise ValueError("Entity search index exceeds 64 MiB; reduce the loaded area")
        yield row
