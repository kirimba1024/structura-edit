from contextlib import contextmanager
import json
from pathlib import Path

import portalocker

from .overview_store import MAX_SNAPSHOT_BYTES


def open_snapshot(path):
    from structura_core.world import JavaWorld
    from structura_core.world_terrain import terrain_stamp

    from .file_state import resource_stamp
    from .overview_store import load_manifest
    from .resources import resolve_assets

    snapshot = load_manifest(path)
    metadata = snapshot['metadata']
    world = JavaWorld(metadata['world'])
    current = terrain_stamp(world.dimensions[metadata['dimension']] / 'region')
    assets = resolve_assets(metadata['assets_option'])
    if (current != tuple(map(tuple, metadata.get('terrain_stamp', ())))
            or str(assets) != metadata['assets'] or json.dumps(resource_stamp(assets)) != json.dumps(metadata['resources'])):
        raise ValueError('World or textures changed; prepare a fresh overview')
    return snapshot


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
