from collections import OrderedDict
from hashlib import blake2b
import pickle
from uuid import uuid4

import numpy as np
from structura_core import state_key
from structura_core.block_array import BlockArray


def section_content(source):
    if not hasattr(source, 'palette_raw') or not source.palette_raw:
        return source
    present = source.present
    if isinstance(present, BlockArray):
        grid = present.array
    else:
        grid = np.full(source.size, -1, np.int32)
        for position, index in present.items():
            grid[position] = index
    used = np.unique(grid)
    states = {int(index): state_key(source.palette_raw[index]) for index in used if index >= 0}
    palette = sorted(set(states.values()))
    indices = {state: index for index, state in enumerate(palette)}
    remap = np.full(len(source.palette_raw) + 1, -1, np.int32)
    for index, state in states.items():
        remap[index + 1] = indices[state]
    data = vars(source).copy()
    data.pop('palette_raw')
    data.update(palette=palette, present=remap[grid + 1])
    return data


class SectionCache:
    def __init__(self, limit=192 * 1024 ** 2, *, max_entries=2048):
        self.limit = limit
        self.max_entries = max_entries
        self.entries = OrderedDict()
        self.bytes = 0
        self.bank = None
        self.generation = ""

    def key(self, source, bounds, bank):
        if self.bank is not bank:
            self.entries.clear()
            self.bytes = 0
            self.bank = bank
            self.generation = uuid4().hex
        payload = pickle.dumps((section_content(source), bounds), protocol=5)
        return self.generation, blake2b(payload, digest_size=20).digest()

    def get(self, key):
        entry = self.entries.get(key)
        if entry is not None:
            self.entries.move_to_end(key)
        return entry

    def put(self, key, data):
        size = data["geometry_bytes"]
        if size > self.limit:
            return
        previous = self.entries.pop(key, None)
        if previous is not None:
            self.bytes -= previous["geometry_bytes"]
        while self.entries and (self.bytes + size > self.limit or len(self.entries) >= self.max_entries):
            self.bytes -= self.entries.popitem(last=False)[1]["geometry_bytes"]
        self.entries[key] = data
        self.bytes += size
