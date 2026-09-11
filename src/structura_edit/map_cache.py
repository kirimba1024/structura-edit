import hashlib
import io
import json
import sqlite3
from math import isqrt
from contextlib import closing, contextmanager
from pathlib import Path
from time import time

import numpy as np
from PIL import Image

from .appearance import MAP_BACKGROUND
from .map_projection import VIEWS, depth_axis, plane_size, project, slice_bounds
from .map_images import MAP_RENDER_VERSION, MAP_TEXTURE_SIZE
from .file_state import fingerprint, resource_stamp
from .loading import MAP_TILE_SIZE as TILE_SIZE, MAX_MAP_VISIBLE_TILES as MAX_VISIBLE_TILES


MAX_DISK_BYTES = 48 * 1024**2
MAX_TILES = 4096
MAX_READ_PIXELS = 16_777_216
MAP_COVERAGE_VERSION = 1


def map_spec(session, assets, path, *, cut=None, preview=False):
    if path is None or not hasattr(session, "map_identity"):
        return None
    resource = (str(Path(assets).resolve()), resource_stamp(assets)) if assets else None
    identity = json.dumps((session.map_identity, resource, MAP_BACKGROUND, MAP_RENDER_VERSION, MAP_COVERAGE_VERSION), sort_keys=True)
    space = hashlib.sha256(identity.encode()).hexdigest()
    slabs = {}
    bounds = {}
    for view in VIEWS:
        axis = depth_axis(view)
        lower, upper = slice_bounds(session.size, cut, view)
        bounds[view] = lower, upper
        slabs[view] = f"{view}:{session.origin[axis] + lower}:{session.origin[axis] + upper}"
    return dict(path=str(path), space=space, slabs=slabs, bounds=bounds, origin=session.origin, size=session.size,
                loaded=session.loaded_chunks, stamps=session.map_stamps, volatile=session.dirty or preview)


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


def decode(data, scale=MAP_TEXTURE_SIZE):
    with Image.open(io.BytesIO(data)) as image:
        if image.size != (TILE_SIZE * MAP_TEXTURE_SIZE,) * 2 or image.mode != "RGBA":
            raise ValueError("Invalid map tile")
        if scale != MAP_TEXTURE_SIZE:
            image = image.resize((TILE_SIZE * scale,) * 2, Image.Resampling.BOX)
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
    lower, upper = spec["bounds"][view]
    if lower == upper:
        return np.zeros(tuple(reversed(plane_size(spec["size"], view))), dtype=bool)
    columns = np.zeros((sz, sx), dtype=bool)
    for cx, cz in spec["loaded"]:
        left, top = cx * 16 - x, cz * 16 - z
        lo_x, hi_x = max(0, left), min(sx, left + 16)
        lo_z, hi_z = max(0, top), min(sz, top + 16)
        if lo_x < hi_x and lo_z < hi_z:
            columns[lo_z:hi_z, lo_x:hi_x] = True
    if view in ("top", "bottom"):
        return columns
    horizontal = columns[lower:upper, :].all(axis=0) if view in ("north", "south") else columns[:, lower:upper].all(axis=1)
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
            scale = MAP_TEXTURE_SIZE
            pixels = np.array(Image.fromarray(pixels).resize((width * scale, height * scale), Image.Resampling.NEAREST))
            a = project(spec["origin"], (0, 0, 0), view)
            b = project(tuple(p + s for p, s in zip(spec["origin"], spec["size"])), (0, 0, 0), view)
            left, top = min(a[0], b[0]), min(a[1], b[1])
            for y in range(top // TILE_SIZE * TILE_SIZE, top + height, TILE_SIZE):
                for x in range(left // TILE_SIZE * TILE_SIZE, left + width, TILE_SIZE):
                    key = spec["space"], spec["slabs"][view], x, y
                    row = db.execute("SELECT image, stamps FROM tiles WHERE space=? AND slab=? AND x=? AND y=?", key).fetchone()
                    try:
                        tile = decode(row[0]) if row else np.zeros((TILE_SIZE * scale, TILE_SIZE * scale, 4), dtype=np.uint8)
                        stamps = json.loads(row[1]) if row else {}
                    except (ValueError, OSError):
                        tile, stamps = np.zeros((TILE_SIZE * scale, TILE_SIZE * scale, 4), dtype=np.uint8), {}
                    stamps.update(spec["stamps"])
                    lo_x, lo_y = max(left, x), max(top, y)
                    hi_x, hi_y = min(left + width, x + TILE_SIZE), min(top + height, y + TILE_SIZE)
                    tile[(lo_y - y) * scale:(hi_y - y) * scale, (lo_x - x) * scale:(hi_x - x) * scale] = (
                        pixels[(lo_y - top) * scale:(hi_y - top) * scale, (lo_x - left) * scale:(hi_x - left) * scale])
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


def read_tiles(spec, areas, scales=None):
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
            scale = min((scales or {}).get(view, 1), MAP_TEXTURE_SIZE,
                        max(1, isqrt(MAX_READ_PIXELS // max(1, len(areas) * len(rows) * TILE_SIZE**2))))
            for rowid, x, y, image in rows:
                try:
                    result[view, x, y] = decode(image, scale)
                except (ValueError, OSError):
                    db.execute("DELETE FROM tiles WHERE rowid=?", (rowid,))
                    continue
                db.execute("UPDATE tiles SET used=? WHERE rowid=?", (time(), rowid))
    return result
