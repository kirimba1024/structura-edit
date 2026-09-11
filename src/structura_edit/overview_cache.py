from contextlib import contextmanager
import json
from pathlib import Path

import portalocker

from .overview_store import MAX_SNAPSHOT_BYTES


def snapshot_lease(path):
    lease = portalocker.Lock(str(path) + ".lock", flags=portalocker.LOCK_SH | portalocker.LOCK_NB, timeout=0)
    lease.acquire()
    return lease


@contextmanager
def snapshot_build_slot(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    try:
        lock = portalocker.Lock(directory / "build.lock", flags=portalocker.LOCK_EX | portalocker.LOCK_NB, timeout=0)
        lock.acquire()
    except portalocker.exceptions.LockException as error:
        raise ValueError("An overview is already being prepared for this dimension") from error
    try:
        current = None
        pointer = directory / "current.json"
        if pointer.is_file():
            try:
                current = json.loads(pointer.read_text(encoding="utf-8")).get("file")
            except (ValueError, AttributeError):
                current = None
        for path in directory.glob("*.sqlite"):
            if path.name == current:
                continue
            lease = portalocker.Lock(str(path) + ".lock", flags=portalocker.LOCK_EX | portalocker.LOCK_NB, timeout=0)
            try:
                with lease:
                    path.unlink(missing_ok=True)
                    Path(str(path) + "-journal").unlink(missing_ok=True)
            except portalocker.exceptions.LockException:
                continue
        remaining = MAX_SNAPSHOT_BYTES - sum(path.stat().st_size for path in directory.glob("*.sqlite"))
        if remaining < 16 * 1024**2:
            raise ValueError("Overview cache is full; close other views or free its cached snapshots")
        yield remaining
    finally:
        lock.release()
