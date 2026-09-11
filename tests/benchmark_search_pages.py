import argparse
import json
import tracemalloc
from pathlib import Path
from statistics import median
from time import perf_counter
from types import SimpleNamespace

import numpy as np

from structura_edit.object_search import BlockIndex, ObjectSearch, search_revision, MATCH_CHUNK, SEARCH_WORK_BYTES


def fixture(count):
    session = SimpleNamespace(_id='benchmark', _state_id='unchanged', revision=0, origin=(0, 0, 0), size=(count, 1, 1))
    index = BlockIndex.__new__(BlockIndex)
    index.positions = np.zeros((count, 3), dtype=np.int32)
    index.positions[:, 0] = np.arange(count, dtype=np.int32)
    index.codes = np.zeros(count, dtype=np.int32)
    index.has_data = np.zeros(count, dtype=bool)
    index.states = ('minecraft:stone',)
    index.query = index.mask = index.cumulative = None
    search = ObjectSearch()
    search.revision, search.blocks = search_revision(session), index
    return session, search


def reference(index, offset):
    allowed = np.array([True], dtype=bool)
    indices = np.flatnonzero(allowed[index.codes])
    return tuple(index.row(i) for i in indices[offset:offset + 64]), len(indices)


def measure(call):
    started = perf_counter()
    result = call()
    return (perf_counter() - started) * 1000, result


def run(count):
    session, search = fixture(count)
    offsets = (0, 64, 128, 192, count - 64)
    before, after = [], []
    first_ms, page = measure(lambda: search.find(session, 'minecraft:', kind='blocks'))
    assert page.total == count
    for _ in range(5):
        for offset in offsets:
            elapsed, expected = measure(lambda: reference(search.blocks, offset))
            before.append(elapsed)
            elapsed, result = measure(lambda: search.find(session, 'minecraft:', kind='blocks', offset=offset))
            after.append(elapsed)
            assert (result.rows, result.total) == expected
    tracemalloc.start()
    reference(search.blocks, 64)
    reference_peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    search.blocks.query = search.blocks.mask = search.blocks.cumulative = None
    tracemalloc.start()
    search.find(session, 'minecraft:', kind='blocks')
    first_peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    tracemalloc.start()
    search.find(session, 'minecraft:', kind='blocks', offset=count - 64)
    page_peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    return dict(blocks=count, first_query_ms=first_ms, previous_page_ms=median(before), cached_page_ms=median(after),
                previous_query_peak_bytes=reference_peak, first_query_peak_bytes=first_peak, cached_page_peak_bytes=page_peak,
                retained_query_bytes=search.blocks.mask.nbytes + search.blocks.cumulative.nbytes,
                reserved_block_bytes=count * 18 + ((count + MATCH_CHUNK - 1) // MATCH_CHUNK + 1) * 8 + SEARCH_WORK_BYTES)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path('/private/tmp/structura-search-pages.json'))
    args = parser.parse_args()
    rows = [run(count) for count in (100_000, 1_000_000, 3_000_000)]
    result = dict(rows=rows, scenario='Prepared NumPy index; all blocks match minecraft:; offsets 0/64/128/192/last page; no GUI, IPC or index construction. Timings and tracemalloc measured separately.')
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
