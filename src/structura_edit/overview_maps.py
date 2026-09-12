import numpy as np
from PIL import ImageColor

from structura_render.color_space import linear_to_srgb, srgb_to_linear

from .overview_store import MAP_SPAN, clip_overview_source, encode_arrays, encode_image
from .height_slice import HeightSlice
from .appearance import MAP_BACKGROUND
from .map_images import MAP_TEXTURE_SIZE, map_faces, map_tiles, render_map


EMPTY_HEIGHT = np.iinfo(np.int32).min
MAP_MIN_LEVEL = -4


def column_image(store, cx, cz, bank, below_y, height_slice):
    low, high = store.db.execute("SELECT MIN(y), MAX(y) FROM blocks WHERE x BETWEEN ? AND ? AND z BETWEEN ? AND ?",
                                (cx - 1, cx, cz - 1, cz)).fetchone()
    height = np.full((16, 16), EMPTY_HEIGHT, np.int32)
    if low is None:
        image = np.full((16 * MAP_TEXTURE_SIZE, 16 * MAP_TEXTURE_SIZE, 4),
                        (*ImageColor.getrgb(MAP_BACKGROUND), 255), np.uint8)
        return image, height
    low, high = low * 16, (high + 1) * 16
    source = store.read_region((cx * 16 - 1, low, cz * 16 - 1), (cx * 16 + 16, high, cz * 16 + 16))
    clip_overview_source(source, low, height_slice)
    if below_y is not None:
        source.present.array[:, max(0, below_y - low):, :] = -1
    tiles = map_tiles(source.palette, map_faces(source, bank), "top", MAP_TEXTURE_SIZE)
    pixels = render_map(source.present.array, "top", (0, source.size[1]), tiles, area=(1, 1, 17, 17))
    visible = (tiles[..., 3] > 0).any(axis=(1, 2))[source.present.array[1:, ::-1, 1:]]
    height[visible.any(axis=1)] = (high - visible.argmax(axis=1))[visible.any(axis=1)]
    image = np.full((*pixels.shape[:2], 4), 255, np.uint8)
    image[..., :3] = pixels
    return image, height


def build_map_pyramid(store, columns, bank, progress, below_y=None, height_slice=HeightSlice(), *, reuse=None):
    keys = set()
    for done, (cx, cz) in enumerate(columns, 1):
        if reuse is not None and reuse.column(cx, cz):
            keys.update((cx * 2 + dx, cz * 2 + dz) for dx in range(2) for dz in range(2))
            progress("Building map", done, len(columns))
            continue
        image, height = column_image(store, cx, cz, bank, below_y, height_slice)
        for dx in range(2):
            for dz in range(2):
                key = cx * 2 + dx, cz * 2 + dz
                pixels = image[dz * MAP_SPAN:(dz + 1) * MAP_SPAN, dx * MAP_SPAN:(dx + 1) * MAP_SPAN]
                store.db.execute("INSERT INTO maps VALUES (?,?,?,?)", (MAP_MIN_LEVEL, *key, encode_image(pixels)))
                keys.add(key)
        store.db.execute("INSERT INTO surfaces VALUES (?,?,?)", (cx, cz, encode_arrays(height=height)))
        progress("Building map", done, len(columns))
        if done % 64 == 0:
            store.db.commit()
    if not keys:
        return 0
    groups = {(x // 8, z // 8) for x, z in columns}
    extent = max(max(p[axis] for p in groups) - min(p[axis] for p in groups) + 1 for axis in (0, 1))
    maximum = max(1, (extent - 1).bit_length())
    for level in range(MAP_MIN_LEVEL + 1, maximum + 1):
        parents = {(x // 2, z // 2) for x, z in keys}
        for x, z in sorted(parents):
            if reuse is not None and reuse.map((level, x, z)):
                continue
            image = np.zeros((MAP_SPAN * 2, MAP_SPAN * 2, 4), np.uint8)
            for dx in range(2):
                for dz in range(2):
                    child = store.read_map((level - 1, x * 2 + dx, z * 2 + dz))
                    if child is not None:
                        image[dz * MAP_SPAN:(dz + 1) * MAP_SPAN, dx * MAP_SPAN:(dx + 1) * MAP_SPAN] = child
            store.db.execute("INSERT INTO maps VALUES (?,?,?,?)", (level, x, z, encode_image(downsample_map(image))))
        keys = parents
        progress("Building map scales", level - MAP_MIN_LEVEL, maximum - MAP_MIN_LEVEL)
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
