from collections import OrderedDict
from hashlib import blake2b
import pickle
from uuid import uuid4


class SectionCache:
    def __init__(self, limit=96 * 1024 ** 2):
        self.limit = limit
        self.entries = OrderedDict()
        self.bytes = 0
        self.bank = None
        self.generation = ""

    def key(self, source, origin, bounds, bank):
        if self.bank is not bank:
            self.entries.clear()
            self.bytes = 0
            self.bank = bank
            self.generation = uuid4().hex
        payload = pickle.dumps((source, origin, bounds), protocol=5)
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
        while self.entries and (self.bytes + size > self.limit or len(self.entries) >= 2048):
            self.bytes -= self.entries.popitem(last=False)[1]["geometry_bytes"]
        self.entries[key] = data
        self.bytes += size
