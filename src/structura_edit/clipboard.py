from dataclasses import dataclass, replace
from types import SimpleNamespace

from structura_core import parse_state

from .cell_data import cell_payload, detached_cell
from .changes import ChangeSet, StaleChangeError, _Cell, _Delta, _position
from .picking import EMPTY


@dataclass(frozen=True)
class Clipboard:
    size: tuple
    cells: tuple
    document_id: str
    revision: int
    selection: object
    data_version: int

    @classmethod
    def capture(cls, edit, selection):
        edit._check_readable(selection)
        if selection.volume > edit.operation_limit:
            raise ValueError("Clipboard exceeds the cell budget; select a smaller region")
        cells = []
        for position in selection.positions():
            cell = edit._cell(position)
            if cell is not None:
                local = tuple(p - lo for p, lo in zip(position, selection.lower))
                cells.append((local, detached_cell(edit._document.source, cell, position)))
        return cls(tuple(hi - lo for lo, hi in zip(selection.lower, selection.upper)), tuple(cells),
                   edit._id, edit.revision, selection, edit._document.source.data_version)

    def transformed(self, *, turns=0, flip=None):
        from .clipboard_transform import transform_clipboard

        return transform_clipboard(self, turns=turns, flip=flip)

    def render_source(self):
        states = {}
        present, block_nbt = {}, {}
        for position, cell in self.cells:
            present[position] = states.setdefault(cell.state, len(states))
            payload = cell_payload(None, cell, position)
            if payload is not None:
                block_nbt[position] = payload
        palette = [parse_state(state) for state in states] or [parse_state("minecraft:air")]
        return SimpleNamespace(size=self.size, present=present, palette_raw=palette,
                               palette=[str(state["Name"]) for state in palette], block_nbt=block_nbt, entities=[])


def place(edit, clipboard, position, *, take=False, include_air=False):
    if edit.readonly:
        raise ValueError("This source is view-only in this release")
    position = _position(position)
    destination = edit.select((position, tuple(p + s for p, s in zip(position, clipboard.size))))
    if destination.volume > edit.operation_limit:
        raise ValueError("Placement exceeds the cell budget")
    if take and (clipboard.document_id != edit._id or clipboard.revision != edit.revision):
        raise StaleChangeError("The source changed; take a fresh selection")
    targets = {}
    if take:
        targets.update((p, _Cell("minecraft:air")) for p in clipboard.selection.positions()
                       if (cell := edit._cell(p)) is not None and cell.state.split("[", 1)[0] not in EMPTY)
    if include_air:
        targets.update((p, _Cell("minecraft:air")) for p in destination.positions())
    for local, cell in clipboard.cells:
        if not include_air and cell.state.split("[", 1)[0] in EMPTY:
            continue
        if clipboard.document_id != edit._id:
            cell = replace(cell, variant=None, origin=None)
        elif cell.origin is not None:
            cell = replace(cell, data=None)
        targets[tuple(p + d for p, d in zip(local, position))] = cell
    change = ChangeSet(edit._id, edit.revision, "Take" if take else "Paste", tuple(
        _Delta(p, edit._cell(p), cell) for p, cell in targets.items() if edit._cell(p) != cell
    ))
    edit._check_change(change)
    return change
