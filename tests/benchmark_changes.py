import argparse
import cProfile
import gc
import json
from pathlib import Path
import pickle
from statistics import median
from time import perf_counter

from building_fixture import building_source
from structura_edit import EditSession


def fixture(floors):
    edit = EditSession.from_structure(building_source())
    edit.apply(edit.stack(edit.select(), floors - 1, (0, 6, 0)))
    edit = EditSession.from_structure(edit.snapshot())
    change = edit.paste(edit.copy(edit.select()), (-40, -3, -32), take=True)
    return edit, change


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--floors", type=int, default=24)
    parser.add_argument("--repeats", type=int, default=7)
    parser.add_argument("--profile", action="store_true")
    args = parser.parse_args()
    if not 2 <= args.floors <= 48 or not 1 <= args.repeats <= 100:
        parser.error("Use 2–48 floors and 1–100 repeats")
    edit, change = fixture(args.floors)
    encoded = pickle.dumps(change, protocol=5)
    restored = pickle.loads(encoded)
    assert restored == change and restored is not change
    edit._check_change(restored)
    actions = dict(validate=lambda: edit._check_change(change), encode=lambda: pickle.dumps(change, protocol=5),
                   decode=lambda: pickle.loads(encoded))
    result = dict(floors=args.floors, cells=len(change), pickle_bytes=len(encoded), profiled=args.profile, stages={})
    for name, action in actions.items():
        gc.collect()
        if args.profile:
            profile = cProfile.Profile()
            profile.runcall(action)
            profile.dump_stats(str(args.output.with_name(args.output.stem + f"-{name}.prof")))
        else:
            samples = []
            for _ in range(args.repeats):
                start = perf_counter()
                value = action()
                samples.append((perf_counter() - start) * 1000)
                del value
            result["stages"][name] = dict(median_ms=median(samples), max_ms=max(samples), samples_ms=samples)
    args.output.write_text(json.dumps(result, indent=2))
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
