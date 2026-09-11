import argparse
import gc
import json
import platform
import resource
import tracemalloc
from itertools import product
from math import ceil, floor
from pathlib import Path
from statistics import median
from time import perf_counter
from unittest.mock import patch

from amulet_nbt import from_snbt
from structura_core import Structure

from structura_edit import EditSession
from structura_edit.paint import paint_stroke, segment_candidates


def bounding_box_candidates(selection, start, stop, radius):
    lower = tuple(max(lo, floor(min(a, b) - radius - 0.5)) for a, b, lo in zip(start, stop, selection.lower))
    upper = tuple(min(hi, ceil(max(a, b) + radius + 0.5) + 1) for a, b, hi in zip(start, stop, selection.upper))
    return product(*(range(lo, hi) for lo, hi in zip(lower, upper)))


def measure(session, points, candidates, repeats):
    selection = session.select()
    with patch('structura_edit.paint.segment_candidates', candidates):
        durations = []
        for _ in range(repeats):
            started = perf_counter()
            change = paint_stroke(session, selection, points, 'minecraft:gold_block', 1)
            durations.append((perf_counter() - started) * 1000)
        positions = change.positions
        del change
        gc.collect()
        tracemalloc.start()
        change = paint_stroke(session, selection, points, 'minecraft:gold_block', 1)
        retained, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        assert positions == change.positions
    work = sum(1 for _ in candidates(selection, points[0], points[0], 1))
    work += sum(1 for _ in candidates(selection, points[0], points[-1], 1))
    return dict(samples=repeats, p50_ms=round(median(durations), 2),
                p95_ms=round(sorted(durations)[ceil(0.95 * repeats) - 1], 2),
                candidates=work, changed=len(positions), python_retained_mib=round(retained / 1024**2, 3),
                python_peak_mib=round(peak / 1024**2, 3)), positions


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--size', type=int, default=512)
    parser.add_argument('--repeats', type=int, default=9)
    parser.add_argument('--output', type=Path, default=Path('/private/tmp/structura-paint-benchmark.json'))
    args = parser.parse_args()
    if not 2 <= args.size <= 700 or args.repeats < 1:
        parser.error('Use size 2–700 and at least one repeat')
    source = Structure.from_root(from_snbt('{DataVersion:3955,size:[1,1,1],palette:[{Name:"minecraft:stone"}],blocks:[],entities:[]}'))
    source.size = (args.size, args.size, 1)
    source.present = dict.fromkeys(product(range(args.size), range(args.size), range(1)), 0)
    session = EditSession.from_structure(source)
    points = ((0.5, 0.5, 0.5), (args.size - 0.5, args.size - 0.5, 0.5))
    results, positions = {}, None
    for name, candidates in (('bounding_box_before', bounding_box_candidates), ('tube_after', segment_candidates)):
        results[name], current = measure(session, points, candidates, args.repeats)
        assert positions is None or positions == current
        positions = current
        print(name, json.dumps(results[name]), flush=True)
    result = dict(python=platform.python_version(), platform=platform.platform(), wall=source.size, radius=1,
                  results=results, process_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if platform.system() == 'Darwin' else 1024),
                  memory_scope='Separate tracemalloc pass after fixture creation; excludes native allocations and existing document')
    args.output.write_text(json.dumps(result, indent=2))
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
