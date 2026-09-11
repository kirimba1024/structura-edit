from __future__ import annotations

from copy import copy, deepcopy
from dataclasses import dataclass
from typing import Dict, Optional, Tuple, TypeVar, Union

from .changes import ChangeSet, StaleChangeError, _Cell
from .history import History
from .session import EditSession
from .task_protocol import ApplyCommand, DocumentCommand, DocumentToken, HistoryCommand, Position
from .world_view import WorldView


BlockKey = Union[Position, Tuple[str, int, int, int]]
CellPair = Tuple[Optional[_Cell], Optional[_Cell]]
Key = TypeVar('Key')
Value = TypeVar('Value')


def compact_change(session: EditSession, command: DocumentCommand) -> Optional[ChangeSet]:
    if type(session) not in (EditSession, WorldView):
        return None
    if isinstance(command, ApplyCommand):
        change = command.change
    elif (isinstance(command, HistoryCommand) and type(command.index) is int
          and 0 <= command.index <= len(session.history.entries)
          and abs(command.index - session.history.cursor) == 1):
        _, change = session.history.get(min(command.index, session.history.cursor))
    else:
        return None
    return change if change.resize is None and not change.entities else None


def _patched(values: Dict[Key, Value], updates: Dict[Key, Optional[Value]]) -> Dict[Key, Value]:
    result = values.copy()
    for key, value in updates.items():
        if value is None:
            result.pop(key, None)
        else:
            result[key] = value
    return result


@dataclass(frozen=True)
class DocumentDelta:
    base: DocumentToken
    world: bool
    cells: Dict[Position, Optional[_Cell]]
    blocks: Dict[BlockKey, Optional[CellPair]]
    history: History
    transition: Optional[Tuple[str, Tuple[Position, ...]]]

    @classmethod
    def capture(cls, session: EditSession, base: DocumentToken, change: ChangeSet, *, local: bool) -> DocumentDelta:
        world = isinstance(session, WorldView)
        keys = []
        positions = []
        for delta in change.changes:
            if world and not local:
                dimension, *position = delta.position
                keys.append(delta.position)
                if dimension != session.dimension:
                    continue
                position = tuple(p - o for p, o in zip(position, session.origin))
            else:
                position = delta.position
                absolute = tuple(p + o for p, o in zip(position, session.origin))
                keys.append((session.dimension, *absolute) if world else absolute)
            if all(0 <= p < size for p, size in zip(position, session.size)):
                positions.append(position)
        blocks = session.world_changes.patch if world else session._saved_changes.blocks
        return cls(base, world, {p: session._cells.get(p) for p in positions},
                   {key: blocks.get(key) for key in keys}, deepcopy(session.history), session._transition)

    def restore(self, session: EditSession, base: DocumentToken, version: Optional[DocumentToken]) -> EditSession:
        if (self.base != base or (session._id, session.revision, session._state_id) !=
                (base.document_id, base.revision, base.state_id) or version is None
                or version.document_id != base.document_id or version.revision not in (base.revision, base.revision + 1)
                or self.world != isinstance(session, WorldView)):
            raise StaleChangeError('The worker delta does not match the document snapshot')
        result = copy(session)
        result._cells = _patched(session._cells, self.cells)
        result._entities = session._entities.copy()
        result.history = self.history
        result.revision, result._state_id = version.revision, version.state_id
        result._transition = self.transition
        if self.world:
            result.world_changes = copy(session.world_changes)
            result.world_changes.patch = _patched(session.world_changes.patch, self.blocks)
            result.world_changes.entities = session.world_changes.entities.copy()
            result.world_changes.history = result.history
            result.world_changes.revision, result.world_changes.state_id = version.revision, version.state_id
        else:
            result._saved_changes = copy(session._saved_changes)
            result._saved_changes.blocks = _patched(session._saved_changes.blocks, self.blocks)
            result._saved_changes.entities = session._saved_changes.entities.copy()
        return result
