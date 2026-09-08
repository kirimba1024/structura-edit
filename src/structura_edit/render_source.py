from itertools import product
from types import SimpleNamespace

from structura_core import parse_state

from .cell_data import cell_payload
from .height_slice import HeightSlice


def preview_session(session, change=None):
    if change is None:
        return session
    branch = session.fork()
    branch.apply(change)
    return branch


class RenderSource:
    def __init__(self, session, height=HeightSlice()):
        self.session = session
        self.height = height
        self.base = session._document.source
        self.palette_raw = list(self.base.palette_raw)
        self.literals = {}
        self.palette = [str(state["Name"]) for state in self.palette_raw]

    def entity_records(self):
        result = {}
        for key, value in self.session._entities.items():
            record = value.unpack()
            if self.height.includes_entity(record, self.session):
                result[key] = record
        return result

    def _index(self, cell):
        if cell.variant is not None:
            return cell.variant
        if cell.state not in self.literals:
            self.literals[cell.state] = len(self.palette_raw)
            self.palette_raw.append(parse_state(cell.state))
            self.palette.append(str(self.palette_raw[-1]["Name"]))
        return self.literals[cell.state]

    def region(self, lower=None, upper=None, *, include_entities=False, include_nbt=True):
        whole = lower is None
        lower = (0, 0, 0) if whole else lower
        upper = self.session.size if upper is None else upper
        positions = self.session.positions() if whole else product(*(range(lo, hi) for lo, hi in zip(lower, upper)))
        present, block_nbt = {}, {}
        low_y, high_y = self.height.interval(self.session)
        for position in positions:
            if not low_y <= position[1] < high_y:
                continue
            cell = self.session._cells.get(position)
            if cell is None:
                index = self.base.present.get(position)
                payload = self.base.block_nbt.get(position) if include_nbt else None
            else:
                index = self._index(cell)
                payload = cell_payload(self.base, cell, position) if include_nbt else None
            if index is not None:
                local = position if whole else tuple(p - lo for p, lo in zip(position, lower))
                present[local] = index
                if payload is not None:
                    block_nbt[local] = payload
        return SimpleNamespace(size=tuple(hi - lo for lo, hi in zip(lower, upper)),
                               palette_raw=self.palette_raw, palette=self.palette,
                               present=present, block_nbt=block_nbt,
                               entities=list(self.entity_records().values()) if include_entities else [])
