import json
from statistics import median
from pathlib import Path
from time import perf_counter

from amulet_nbt import from_snbt
from structura_core import Structure

from structura_edit import EditSession
from structura_edit.cell_data import detached_cell


def session(size, positions):
    source = Structure.from_root(from_snbt('{DataVersion:3955,size:[1,1,1],palette:[{Name:"minecraft:stone"}],blocks:[],entities:[]}'))
    source.size = size
    source.present = dict.fromkeys(positions, 0)
    return EditSession.from_structure(source)


def timed(call):
    times = []
    for _ in range(5):
        start = perf_counter()
        result = call()
        times.append((perf_counter() - start) * 1000)
    return median(times), result


def main():
    edit = session((500_000, 1, 1), ((x, 0, 0) for x in range(500_000)))
    selection = edit.select(((0, 0, 0), (10, 1, 1)))
    before, expected = timed(lambda: edit._change((p for p in edit.positions() if p in selection and edit.state_at(p) == 'minecraft:stone'),
                                                 'minecraft:glass', 'Replace'))
    after, result = timed(lambda: edit.replace(selection, 'minecraft:stone', 'minecraft:glass'))
    assert result == expected
    small = dict(document_blocks=500_000, selection_cells=10, previous_ms=before, adaptive_ms=after)
    edit = session((1000, 10, 100), ((0, 0, 0), (999, 9, 99)))
    edit.operation_limit = 10
    selection = edit.select()
    def dense_capture():
        cells = []
        for position in selection.positions():
            cell = edit._cell(position)
            if cell is not None:
                cells.append((position, detached_cell(edit._document.source, cell, position)))
        return tuple(cells)
    before, expected = timed(dense_capture)
    after, result = timed(lambda: edit.copy(selection))
    assert result.cells == expected
    edit._check_change(edit.paste(result, (0, 0, 0)))
    sparse = dict(selection_cells=selection.volume, stored_blocks=len(result.cells), previous_scan_ms=before, adaptive_copy_ms=after,
                  operation_limit=edit.operation_limit, paste_without_air='accepted')
    report = dict(small_replace=small, sparse_copy=sparse, scenario='Python API, five samples, no GUI or IPC. Previous copy enumeration measured without its old volume rejection; identical stored cells asserted.')
    Path('/private/tmp/structura-sparse-iteration.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
