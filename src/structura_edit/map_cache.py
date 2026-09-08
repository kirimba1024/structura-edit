import hashlib
import io
import json
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path
from time import time

import numpy as np
from PIL import Image

from .appearance import MAP_BACKGROUND
from .map_projection import VIEWS, depth_axis, plane_size, project
from .map_images import MAP_RENDER_VERSION
from .file_state import fingerprint, resource_stamp
from .loading import MAP_TILE_SIZE as TILE_SIZE, MAX_MAP_VISIBLE_TILES as MAX_VISIBLE_TILES


MAX_DISK_BYTES = 48 * 1024**2
MAX_TILES = 4096


def map_spec(session, assets, path):
    if path is None or not hasattr(session, "map_identity"):
        return None
    resource = (str(Path(assets).resolve()), resource_stamp(assets)) if assets else None
    identity = json.dumps((session.map_identity, resource, MAP_BACKGROUND, MAP_RENDER_VERSION), sort_keys=True)
    space = hashlib.sha256(identity.encode()).hexdigest()
    slabs = {}
    for view in VIEWS:
        axis = depth_axis(view)
        slabs[view] = f"{view}:{session.origin[axis]}:{session.origin[axis] + session.size[axis]}"
    return dict(path=str(path), space=space, slabs=slabs, origin=session.origin, size=session.size,
                loaded=session.loaded_chunks, stamps=session.map_stamps, volatile=session.dirty)


@contextmanager
def connect(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path, timeout=2)) as db, db:
        db.execute("PRAGMA journal_size_limit=1048576")
        db.execute("PRAGMA max_page_count=16384")
        db.execute("CREATE TABLE IF NOT EXISTS tiles (space TEXT, slab TEXT, x INTEGER, y INTEGER, "
                   "image BLOB, stamps TEXT, used REAL, PRIMARY KEY(space, slab, x, y))")
        db.execute("BEGIN IMMEDIATE")
        yield db


def decode(data):
    with Image.open(io.BytesIO(data)) as image:
        if image.size != (TILE_SIZE, TILE_SIZE) or image.mode != "RGBA":
            raise ValueError("Invalid map tile")
        return np.array(image)


def invalidate(db, space):
    checked = {}
    for row in db.execute("SELECT rowid, stamps FROM tiles WHERE space=?", (space,)).fetchall():
        try:
            stamps = json.loads(row[1])
        except (TypeError, ValueError):
            db.execute("DELETE FROM tiles WHERE rowid=?", (row[0],))
            continue
        for path in stamps:
            if path not in checked:
                checked[path] = fingerprint(path)
        if any(checked[path] != stamp for path, stamp in stamps.items()):
            db.execute("DELETE FROM tiles WHERE rowid=?", (row[0],))


def known_pixels(spec, view):
    x, _, z = spec["origin"]
    sx, sy, sz = spec["size"]
    columns = np.zeros((sz, sx), dtype=bool)
    for cx, cz in spec["loaded"]:
        left, top = cx * 16 - x, cz * 16 - z
        columns[max(0, top):min(sz, top + 16), max(0, left):min(sx, left + 16)] = True
    if view in ("top", "bottom"):
        return columns
    horizontal = columns.all(axis=0 if view in ("north", "south") else 1)
    if view in ("south", "east"):
        horizontal = horizontal[::-1]
    return np.broadcast_to(horizontal, (sy, len(horizontal)))


def store_maps(spec, images):
    result = {}
    for view, pixels in images.items():
        known = known_pixels(spec, view)
        scale = pixels.shape[0] // known.shape[0]
        alpha = np.repeat(np.repeat(known, scale, axis=0), scale, axis=1).astype(np.uint8) * 255
        result[view] = np.dstack((pixels, alpha))
    if any(fingerprint(path) != stamp for path, stamp in spec["stamps"].items()):
        return result, None
    if spec.get("volatile"):
        return result, spec
    with connect(spec["path"]) as db:
        invalidate(db, spec["space"])
        for view, pixels in result.items():
            width, height = plane_size(spec["size"], view)
            pixels = np.array(Image.fromarray(pixels).resize((width, height), Image.Resampling.BOX))
            a = project(spec["origin"], (0, 0, 0), view)
            b = project(tuple(p + s for p, s in zip(spec["origin"], spec["size"])), (0, 0, 0), view)
            left, top = min(a[0], b[0]), min(a[1], b[1])
            for y in range(top // TILE_SIZE * TILE_SIZE, top + height, TILE_SIZE):
                for x in range(left // TILE_SIZE * TILE_SIZE, left + width, TILE_SIZE):
                    key = spec["space"], spec["slabs"][view], x, y
                    row = db.execute("SELECT image, stamps FROM tiles WHERE space=? AND slab=? AND x=? AND y=?", key).fetchone()
                    try:
                        tile = decode(row[0]) if row else np.zeros((TILE_SIZE, TILE_SIZE, 4), dtype=np.uint8)
                        stamps = json.loads(row[1]) if row else {}
                    except (ValueError, OSError):
                        tile, stamps = np.zeros((TILE_SIZE, TILE_SIZE, 4), dtype=np.uint8), {}
                    stamps.update(spec["stamps"])
                    lo_x, lo_y = max(left, x), max(top, y)
                    hi_x, hi_y = min(left + width, x + TILE_SIZE), min(top + height, y + TILE_SIZE)
                    tile[lo_y - y:hi_y - y, lo_x - x:hi_x - x] = pixels[lo_y - top:hi_y - top, lo_x - left:hi_x - left]
                    if not tile[:, :, 3].any():
                        db.execute("DELETE FROM tiles WHERE space=? AND slab=? AND x=? AND y=?", key)
                        continue
                    output = io.BytesIO()
                    Image.fromarray(tile).save(output, format="PNG")
                    db.execute("INSERT OR REPLACE INTO tiles VALUES (?, ?, ?, ?, ?, ?, ?)",
                               (*key, output.getvalue(), json.dumps(stamps, sort_keys=True), time()))
        rows = db.execute("SELECT rowid, length(image) + length(stamps) + 256 FROM tiles ORDER BY used DESC").fetchall()
        total = 0
        for index, (rowid, size) in enumerate(rows):
            total += size
            if index >= MAX_TILES or total > MAX_DISK_BYTES:
                db.execute("DELETE FROM tiles WHERE rowid=?", (rowid,))
    return result, spec


def read_tiles(spec, areas):
    if not Path(spec["path"]).exists():
        return {}
    result = {}
    with connect(spec["path"]) as db:
        for view, (left, top, right, bottom) in areas.items():
            rows = db.execute(
                "SELECT rowid, x, y, image FROM tiles WHERE space=? AND slab=? "
                "AND x < ? AND x + ? > ? AND y < ? AND y + ? > ? "
                "ORDER BY ABS(x - ?) + ABS(y - ?) LIMIT ?",
                (spec["space"], spec["slabs"][view], right, TILE_SIZE, left, bottom, TILE_SIZE, top,
                 (left + right) / 2, (top + bottom) / 2, MAX_VISIBLE_TILES // len(areas))).fetchall()
            for rowid, x, y, image in rows:
                try:
                    result[view, x, y] = decode(image)
                except (ValueError, OSError):
                    db.execute("DELETE FROM tiles WHERE rowid=?", (rowid,))
                    continue
                db.execute("UPDATE tiles SET used=? WHERE rowid=?", (time(), rowid))
    return result
