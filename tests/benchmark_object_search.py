import argparse
import json
from pathlib import Path
from statistics import median
from time import perf_counter, sleep

from structura_edit.jobs import Worker
from structura_edit.object_search import ObjectSearch
from structura_edit.source_loading import open_source


def timed_search(worker, session, text):
    started = perf_counter()
    worker.submit("object_search", session=session.fork(), query={"text": text})
    while perf_counter() - started < 30:
        result = worker.poll()
        if result is not None:
            assert result[0], result[1]
            return (perf_counter() - started) * 1000
        sleep(0.001)
    raise AssertionError("Object search timed out")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    parser.add_argument("--output", type=Path, default=Path("/private/tmp/structura-object-search-benchmark.json"))
    args = parser.parse_args()
    session = open_source(args.path)
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
    finally:
        worker.close()
    result = dict(blocks=len(search.blocks.positions), objects=page.total, index_ms=round(index_ms, 2),
                  index_array_bytes=sum(array.base.nbytes if array.base is not None else array.nbytes
                                        for array in (search.blocks.positions, search.blocks.codes, search.blocks.has_data)),
                  cached_query_ms_median=round(median(samples), 2), worker_first_ms=round(cold, 2),
                  worker_query_ms_median=round(median(elapsed), 2), worker_query_ms_max=round(max(elapsed), 2))
    args.output.write_text(json.dumps(result, indent=2))
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
