from functools import lru_cache

import numpy as np

from structura_render.lod_geometry import average_rgba
from structura_render.color_space import linear_to_srgb, srgb_to_linear

from .overview_store import MAP_SPAN, encode_arrays, encode_image
from .height_slice import HeightSlice


EMPTY_HEIGHT = np.iinfo(np.int32).min
VOID_COLOR = (27, 33, 42)


def build_map_pyramid(store, columns, bank, progress, below_y=None, height_slice=HeightSlice()):
    from structura_render.block_colours import block_color
    from structura_render.atlas import face_texture_key

    @lru_cache(maxsize=8192)
    def color_for(name):
        faces = bank.resolve(name) or {}
        image = faces.get(face_texture_key("up", faces)) if faces else None
        return average_rgba(image) if image is not None else np.asarray((*block_color(name, "family"), 255), np.uint8)

    groups = {}
    for x, z in columns:
        groups.setdefault((x // 8, z // 8), []).append((x, z))
    for done, ((tx, tz), chunks) in enumerate(sorted(groups.items()), 1):
        image = np.zeros((MAP_SPAN, MAP_SPAN, 4), np.uint8)
        for cx, cz in chunks:
            colors = np.zeros((16, 16, 3), np.float64)
            remaining = np.ones((16, 16), np.float64)
            height = np.full((16, 16), EMPTY_HEIGHT, np.int32)
            sections = store.db.execute("SELECT y FROM blocks WHERE x=? AND z=? ORDER BY y DESC", (cx, cz)).fetchall()
            for (sy,) in sections:
                if below_y is not None and sy * 16 >= below_y:
                    continue
                source = store.read_region((cx * 16, sy * 16, cz * 16), (cx * 16 + 16, sy * 16 + 16, cz * 16 + 16))
                palette = np.asarray([*(color_for(name) for name in source.palette), (0, 0, 0, 0)], np.float64)
                for ly in range(15, -1, -1):
                    y = sy * 16 + ly
                    if below_y is not None and y >= below_y:
                        continue
                    if height_slice.mode != "all" and (y > height_slice.y or (height_slice.mode == "layer" and y < height_slice.y)):
                        continue
                    pixels = palette[source.present.array[:, ly, :]]
                    alpha = pixels[..., 3] / 255
                    visible = alpha > 0
                    height[(height == EMPTY_HEIGHT) & visible] = y + 1
                    colors += pixels[..., :3] * (remaining * alpha)[..., None]
                    remaining *= 1 - alpha
                if (remaining < 1 / 255).all():
                    break
            colors += remaining[..., None] * VOID_COLOR
            result = np.full((16, 16, 4), 255, np.uint8)
            result[..., :3] = np.rint(colors).clip(0, 255).astype(np.uint8)
            x, z = (cx % 8) * 16, (cz % 8) * 16
            image[z:z + 16, x:x + 16] = result.transpose(1, 0, 2)
            store.db.execute("INSERT INTO surfaces VALUES (?,?,?)", (cx, cz, encode_arrays(height=height)))
        store.db.execute("INSERT INTO maps VALUES (?,?,?,?)", (0, tx, tz, encode_image(image)))
        progress("Building map", done, len(groups))
    if not groups:
        return 0
    extent = max(max(p[axis] for p in groups) - min(p[axis] for p in groups) + 1 for axis in (0, 1))
    maximum = max(1, (extent - 1).bit_length())
    keys = set(groups)
    for level in range(1, maximum + 1):
        parents = {(x // 2, z // 2) for x, z in keys}
        for x, z in sorted(parents):
            image = np.zeros((MAP_SPAN * 2, MAP_SPAN * 2, 4), np.uint8)
            for dx in range(2):
                for dz in range(2):
                    child = store.read_map((level - 1, x * 2 + dx, z * 2 + dz))
                    if child is not None:
                        image[dz * MAP_SPAN:(dz + 1) * MAP_SPAN, dx * MAP_SPAN:(dx + 1) * MAP_SPAN] = child
            store.db.execute("INSERT INTO maps VALUES (?,?,?,?)", (level, x, z, encode_image(downsample_map(image))))
        keys = parents
    return maximum


def downsample_map(image):
    colors = image.astype(np.float64) / 255
    linear = srgb_to_linear(colors[..., :3])
    alpha = colors[..., 3:4]
    size = image.shape[0] // 2
    weights = alpha.reshape(size, 2, size, 2, 1).sum(axis=(1, 3))
    total = (linear * alpha).reshape(size, 2, size, 2, 3).sum(axis=(1, 3))
    linear = total / np.maximum(weights, 1e-12)
    rgb = linear_to_srgb(linear)
    return np.rint(np.concatenate((rgb, weights / 4), axis=2).clip(0, 1) * 255).astype(np.uint8)
