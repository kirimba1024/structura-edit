from concurrent.futures import ThreadPoolExecutor

import numpy as np

from structura_edit.map_image_cache import MapImageCache


def test_decoded_cache_reuses_tiles_isolates_snapshots_and_bounds_memory(monkeypatch):
    reads = []
    class Store:
        def __init__(self, path):
            self.path = path

        def read_map(self, key):
            reads.append((self.path, key))
            return np.full((4, 4, 4), key[1], np.uint8) if key[1] >= 0 else None

        def close(self):
            pass

    monkeypatch.setattr('structura_edit.map_image_cache.OverviewStore', Store)
    cache = MapImageCache(limit=128, max_entries=3)
    keys = [(0, 1, 0), (0, 2, 0), (0, -1, 0)]
    with ThreadPoolExecutor(max_workers=1) as worker:
        first = worker.submit(cache.read, 'first', keys).result()
        second = worker.submit(cache.read, 'first', keys).result()
        assert len(reads) == 3 and first.keys() == second.keys()
        assert first[keys[0]].constBits() == second[keys[0]].constBits()
        worker.submit(cache.read, 'next', keys).result()
        assert len(reads) == 6 and cache.bytes <= 128 and len(cache.entries) <= 3
    assert first[keys[0]].pixelColor(0, 0).red() == 1
