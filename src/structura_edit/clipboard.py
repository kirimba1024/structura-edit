from dataclasses import dataclass, field
from types import SimpleNamespace

from structura_core import parse_state

from .cell_data import cell_payload, detached_cell
from .picking import EMPTY


@dataclass(frozen=True)
class Clipboard:
    size: tuple
    cells: tuple
    document_id: str
    revision: int
    selection: object
    data_version: int
    origin: tuple = (0, 0, 0)
    sources: tuple = ()
    entities: tuple = ()
    excluded_players: int = 0
    dimension: object = None
    block_count: int = field(init=False)

    def __post_init__(self):
        object.__setattr__(self, "block_count", sum(cell.state.split("[", 1)[0] not in EMPTY for _, cell in self.cells))
        if not self.sources:
            object.__setattr__(self, "sources", tuple(tuple(p + lo for p, lo in zip(local, self.selection.lower)) for local, _ in self.cells))

    @classmethod
    def capture(cls, edit, selection, *, include_blocks=True, include_entities=True):
        from .clipboard_entities import capture_entities

        edit._check_readable(selection)
        if include_blocks and selection.volume > edit.operation_limit:
            raise ValueError("Clipboard exceeds the cell budget; select a smaller region")
        cells = []
        for position in selection.positions() if include_blocks else ():
            cell = edit._cell(position)
            if cell is not None:
                local = tuple(p - lo for p, lo in zip(position, selection.lower))
                cells.append((local, detached_cell(edit._document.source, cell, position)))
        entities, players = capture_entities(edit, selection) if include_entities else ((), 0)
        if len(cells) + len(entities) > edit.operation_limit:
            raise ValueError("Clipboard exceeds the object budget; select a smaller region")
        return cls(tuple(hi - lo for lo, hi in zip(selection.lower, selection.upper)), tuple(cells),
                   edit._id, edit.revision, selection, edit._document.source.data_version, edit.origin,
                   entities=entities, excluded_players=players, dimension=getattr(edit, "dimension", None))

    def can_take_from(self, edit):
        return (self.document_id, self.revision, self.origin, self.dimension) == (
            edit._id, edit.revision, edit.origin, getattr(edit, "dimension", None))

    def transformed(self, *, turns=0, flip=None):
        from .clipboard_transform import transform_clipboard

        return transform_clipboard(self, turns=turns, flip=flip)

    def render_source(self, *, include_blocks=True, include_entities=True):
        states = {}
        present, block_nbt = {}, {}
        for position, cell in self.cells if include_blocks else ():
            present[position] = states.setdefault(cell.state, len(states))
            payload = cell_payload(None, cell, position)
            if payload is not None:
                block_nbt[position] = payload
        palette = [parse_state(state) for state in states] or [parse_state("minecraft:air")]
        return SimpleNamespace(size=self.size, present=present, palette_raw=palette,
                               palette=[str(state["Name"]) for state in palette], block_nbt=block_nbt,
                               entities=[data.unpack() for _, data in self.entities] if include_entities else [])
