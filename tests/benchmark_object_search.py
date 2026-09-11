import argparse
import json
import pickle
from pathlib import Path
from statistics import median
from time import perf_counter, sleep

from structura_edit.jobs import Worker
from structura_edit.task_protocol import TaskSuccess, ObjectSearchCommand
from structura_edit.object_search import ObjectSearch
from structura_edit.source_loading import open_source


def timed_search(worker, session, text, *, offset=0):
    started = perf_counter()
    worker.submit_document(ObjectSearchCommand(text=text, offset=offset), session)
    while perf_counter() - started < 30:
        result = worker.poll()
        if result is not None:
            assert isinstance(result, TaskSuccess), result
            return (perf_counter() - started) * 1000
        sleep(0.001)
    raise AssertionError("Object search timed out")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?")
    parser.add_argument("--synthetic-blocks", type=int)
    parser.add_argument("--output", type=Path, default=Path("/private/tmp/structura-object-search-benchmark.json"))
    args = parser.parse_args()
    if args.synthetic_blocks:
        from amulet_nbt import from_snbt
        from structura_core import Structure
        from structura_edit import EditSession

        source = Structure.from_root(from_snbt('{DataVersion:3955,size:[1,1,1],palette:[{Name:"minecraft:stone"}],blocks:[],entities:[]}'))
        source.size = (args.synthetic_blocks, 1, 1)
        source.present = {(x, 0, 0): 0 for x in range(args.synthetic_blocks)}
        session = EditSession.from_structure(source)
    elif args.path:
        session = open_source(args.path)
    else:
        parser.error("Provide a source path or --synthetic-blocks")
    search = ObjectSearch()
    started = perf_counter()
    page = search.find(session)
    index_ms = (perf_counter() - started) * 1000
    samples = []
    words = ("stone", "oak", "chest", "minecraft:", "no_such_mod:") * 4
    for text in words:
        started = perf_counter()
        search.find(session, text)
        samples.append((perf_counter() - started) * 1000)
    worker = Worker()
    try:
        cold = timed_search(worker, session, "")
        elapsed = [timed_search(worker, session, text) for text in words]
        pages = [timed_search(worker, session, "minecraft:", offset=offset) for offset in (0, 64, 128, 192)]
        page_request_bytes = len(pickle.dumps(ObjectSearchCommand(text="minecraft:", offset=64)))
    finally:
        worker.close()
    result = dict(worker_page_ms=pages, page_command_bytes=page_request_bytes, reserved_search_bytes=search.blocks.reserved_bytes + search.entity_bytes, blocks=len(search.blocks.positions), objects=page.total, index_ms=round(index_ms, 2),
                  index_array_bytes=sum(array.base.nbytes if array.base is not None else array.nbytes
                                        for array in (search.blocks.positions, search.blocks.codes, search.blocks.has_data)),
                  cached_query_ms_median=round(median(samples), 2), worker_first_ms=round(cold, 2),
                  worker_query_ms_median=round(median(elapsed), 2), worker_query_ms_max=round(max(elapsed), 2))
    args.output.write_text(json.dumps(result, indent=2))
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
