from dataclasses import dataclass
from sys import getsizeof
from typing import Optional

import numpy as np

from .picking import EMPTY


PAGE_SIZE = 64
MAX_INDEX_BYTES = 64 * 1024**2


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
    def __init__(self, session):
        source = session._document.source
        capacity = len(source.present) + len(session._cells)
        if capacity * 17 > MAX_INDEX_BYTES:
            raise ValueError("Object search exceeds 64 MiB; reduce the loaded area or search Entities only")
        self.positions = np.empty((capacity, 3), dtype=np.int32)
        self.codes = np.empty(capacity, dtype=np.int32)
        self.has_data = np.empty(capacity, dtype=bool)
        states = dict.fromkeys(session._states)
        states.update((cell.state, None) for cell in session._cells.values() if cell is not None)
        self.states = tuple(states)
        codes = {state: index for index, state in enumerate(self.states)}
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

    def matches(self, words, kind, selection):
        states = np.array([matches_text(state, words) for state in self.states], dtype=bool)
        mask = states[self.codes]
        if kind == "data":
            mask &= self.has_data
        if selection is not None:
            for axis in range(3):
                mask &= (self.positions[:, axis] >= selection.lower[axis]) & (self.positions[:, axis] < selection.upper[axis])
        return np.flatnonzero(mask)

    def row(self, index):
        return ObjectMatch("block", self.states[self.codes[index]], tuple(map(int, self.positions[index])),
                           has_data=bool(self.has_data[index]))


def matches_text(identity, words):
    text = identity.casefold().replace("_", " ")
    return all(word in text for word in words)


class ObjectSearch:
    def __init__(self):
        self.revision = self.blocks = self.entities = None

    def find(self, session, text="", *, kind="all", selection=None, offset=0, limit=PAGE_SIZE):
        if kind not in ("all", "entities", "blocks", "data"):
            raise ValueError("Search type must be all, entities, blocks or data")
        if not isinstance(text, str) or len(text) > 256:
            raise ValueError("Search text must contain at most 256 characters")
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= PAGE_SIZE:
            raise ValueError(f"Use a non-negative offset and a page size from 1 to {PAGE_SIZE}")
        if selection is not None:
            session._check_selection(selection)
        revision = search_revision(session)
        if self.revision != revision:
            self.revision, self.blocks, self.entities = revision, None, None
        words = text.casefold().replace("_", " ").split()
        entities, indices = [], ()
        if kind in ("all", "entities"):
            if self.entities is None:
                self.entities = tuple(entity_matches(session))
            entities = [row for row in self.entities if matches_text(row.identity, words)
                        and (selection is None or row.position in selection)]
        if kind != "entities":
            if self.blocks is None:
                self.blocks = BlockIndex(session)
            indices = self.blocks.matches(words, kind, selection)
        rows = list(entities[offset:offset + limit])
        start = max(0, offset - len(entities))
        rows.extend(self.blocks.row(index) for index in indices[start:start + limit - len(rows)])
        return ObjectPage(tuple(rows), len(entities) + len(indices), offset)


def entity_matches(session):
    used = 0
    for key, data in session._entities.items():
        record = data.unpack()
        identity = str(record["nbt"].get("id", "entity"))
        row = ObjectMatch("entity", identity, tuple(float(value) for value in record["pos"]), key, True)
        used += sum(map(getsizeof, (row, row.__dict__, row.position, *row.position, identity, key))) + 8
        if used > MAX_INDEX_BYTES:
            raise ValueError("Entity search index exceeds 64 MiB; reduce the loaded area")
        yield row
