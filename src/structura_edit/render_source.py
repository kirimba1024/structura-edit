from itertools import product
from types import SimpleNamespace

import numpy as np

from structura_core import parse_state
from structura_core.block_array import BlockArray

from .cell_data import cell_payload
from .height_slice import HeightSlice
from .loading import CHUNK_SIZE


def preview_session(session, change=None):
    if change is None:
        return session
    branch = session.fork()
    if branch.readonly:
        raise ValueError("This source is view-only in this release")
    branch._check_change(change)
    if change:
        branch._apply_cells(change)
    return branch


class RenderSource:
    def __init__(self, session, height=HeightSlice()):
        self.session = session
        self.height = height
        self.base = session._document.source
        self.palette_raw = list(self.base.palette_raw)
        self.literals = {}
        self.palette = [str(state["Name"]) for state in self.palette_raw]
        self.grid = None
        self.grid_offset = 0
        halo = getattr(session, "_render_halo", None)
        self.halo = halo if halo is not None and (halo.origin, halo.size) == (session.origin, session.size) else None

    def prepare_grid(self):
        size = self.session.size
        if isinstance(self.base.present, BlockArray):
            self.grid = self.base.present.array.copy()
        else:
            self.grid = np.full(size, -1, dtype=np.int32)
            sy, sz = size[1:]
            indices = np.fromiter((x * sy * sz + y * sz + z for x, y, z in self.base.present), dtype=np.int64, count=len(self.base.present))
            self.grid.ravel()[indices] = np.fromiter(self.base.present.values(), dtype=np.int32, count=len(self.base.present))
        for position, cell in self.session._cells.items():
            if cell is not None:
                self.grid[position] = self._index(cell)
        payloads = self.base.block_nbt.copy()
        for position, cell in self.session._cells.items():
            if cell is not None:
                payload = cell_payload(self.base, cell, position)
                if payload is None:
                    payloads.pop(position, None)
                else:
                    payloads[position] = payload
        self.grid_nbt = {}
        for position, payload in payloads.items():
            key = tuple(v // CHUNK_SIZE for v in position)
            self.grid_nbt.setdefault(key, {})[position] = payload
        low, high = self.height.interval(self.session)
        self.grid[:, :low, :] = -1
        self.grid[:, high:, :] = -1
        halo = self.halo
        if halo is not None:
            from .world_halo import halo_updates

            halo = halo.updated(halo_updates(self.session))
            self.grid = np.pad(self.grid, 1, constant_values=-1)
            self.grid_offset = 1
            mapping = np.asarray([*(self._state_index(state) for state in halo.palette), -1], np.int32)
            for position, array in halo.faces:
                slices = tuple(slice(p + 1, p + 1 + size) for p, size in zip(position, array.shape))
                self.grid[slices] = mapping[array]
            if self.height.mode != "all":
                self.grid[:, :low + 1, :] = -1
                self.grid[:, high + 1:, :] = -1

    def _grid_region(self, lower, upper, include_nbt):
        grid = self.grid[tuple(slice(lo + self.grid_offset, hi + self.grid_offset) for lo, hi in zip(lower, upper))]
        present = BlockArray(grid.copy())
        block_nbt = {}
        if include_nbt:
            keys = product(*(range(lo // CHUNK_SIZE, (hi - 1) // CHUNK_SIZE + 1) for lo, hi in zip(lower, upper)))
            for key in keys:
                for position, payload in self.grid_nbt.get(key, {}).items():
                    local = tuple(p - lo for p, lo in zip(position, lower))
                    if local in present:
                        block_nbt[local] = payload
        return SimpleNamespace(size=grid.shape, palette_raw=self.palette_raw, palette=self.palette,
                               present=present, block_nbt=block_nbt, entities=[], world=hasattr(self.session, "dimension"))

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
        return self._state_index(cell.state)

    def _state_index(self, state):
        if state not in self.literals:
            self.literals[state] = len(self.palette_raw)
            self.palette_raw.append(parse_state(state))
            self.palette.append(str(self.palette_raw[-1]["Name"]))
        return self.literals[state]

    def region(self, lower=None, upper=None, *, include_entities=False, include_nbt=True):
        if self.grid is None and (self.halo is not None
                                 or lower is None and isinstance(self.base.present, BlockArray)):
            self.prepare_grid()
        if self.grid is not None:
            source = self._grid_region(lower or (0, 0, 0), upper or self.session.size, include_nbt)
            if include_entities:
                source.entities = list(self.entity_records().values())
            return source
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
                               present=present, block_nbt=block_nbt, world=hasattr(self.session, "dimension"),
                               entities=list(self.entity_records().values()) if include_entities else [])
