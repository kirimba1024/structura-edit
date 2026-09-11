import argparse
import json
import pickle
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter
from types import SimpleNamespace

from amulet_nbt import from_snbt
from structura_core import Structure
from structura_core.world import WorldRegion

from structura_edit.changes import _Cell
from structura_edit.world_view import WorldView


def world_view(path, pending):
    source = Structure.from_root(from_snbt('''{DataVersion:3955, size:[16,4,16],
        palette:[{Name:"minecraft:stone"}], blocks:[{pos:[0,0,0],state:0}], entities:[]}'''))
    dimension = 'minecraft:overworld'
    world = SimpleNamespace(path=path, dimensions={dimension: path}, name='Patch benchmark')
    region = WorldRegion(source, frozenset({(0, 0)}), frozenset(), (), dimension, (0, 0, 0), 0, 16)
    view = WorldView(world, region)
    pair = _Cell('minecraft:stone'), _Cell('minecraft:gold_block')
    view.world_changes.patch = {(dimension, i + 32 if i else 0, 0, 0): pair for i in range(pending)}
    view._sync_changes()
    return view


def measure(view, repeats):
    samples = {name: [] for name in ('apply', 'undo', 'redo')}
    initial = view.state_at((0, 0, 0))
    count = len(view.world_changes.patch)
    for _ in range(repeats):
        change = view.set_block((0, 0, 0), 'minecraft:glass')
        for name, action in (('apply', lambda: view.apply(change)), ('undo', view.undo), ('redo', view.redo)):
            started = perf_counter()
            assert action()
            samples[name].append((perf_counter() - started) * 1000)
            assert view.state_at((0, 0, 0)) == (initial if name == 'undo' else 'minecraft:glass')
        assert view.undo() and len(view.world_changes.patch) == count
    started = perf_counter()
    branch = view.fork()
    fork_ms = (perf_counter() - started) * 1000
    started = perf_counter()
    payload = pickle.dumps(branch, protocol=5)
    pickle_ms = (perf_counter() - started) * 1000
    return dict(pending=count, stages={name: dict(median_ms=median(values), samples_ms=values) for name, values in samples.items()},
                fork_ms=fork_ms, pickle_ms=pickle_ms, pickle_bytes=len(payload))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path('/private/tmp/structura-world-patch.json'))
    parser.add_argument('--repeats', type=int, default=5)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error('--repeats must be positive')
    rows = []
    with TemporaryDirectory(prefix='structura-world-patch-') as temporary:
        for count in (0, 100_000, 300_000, 500_000):
            row = measure(world_view(Path(temporary), count), args.repeats)
            rows.append(row)
            print(json.dumps(row), flush=True)
    result = dict(rows=rows, repeats=args.repeats,
                  scenario='Python API, one loaded block, remaining synthetic patch outside the view; real SQLite history; no GUI, IPC or world writes')
    args.output.write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
