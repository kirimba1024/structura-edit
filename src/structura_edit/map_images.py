import math

import numpy as np
from PIL import Image, ImageColor

from .appearance import MAP_BACKGROUND
from .loading import check_preview_budget
from .map_projection import VIEWS, plane_size
from .resources import texture_bank


MAP_RENDER_VERSION = 2


def _composite(data, tiles):
    occupied = data >= 0
    depth = occupied.argmax(axis=-1).ravel()
    active = np.flatnonzero(occupied.any(axis=-1))
    colors = np.zeros((depth.size, *tiles.shape[1:3], 3), dtype=np.float32)
    remaining = np.ones((*colors.shape[:-1], 1), dtype=np.float32)
    while active.size:
        row, column = np.divmod(active, data.shape[1])
        layer = tiles[data[row, column, depth[active]]]
        colors[active] += remaining[active] * layer[..., :3]
        remaining[active] *= 1 - layer[..., 3:4]
        depth[active] += 1
        active = active[(depth[active] < data.shape[-1]) & (remaining[active] > 1 / 255).any(axis=(1, 2, 3))]
    return colors, remaining


def build_maps(session, change=None, assets=None, max_pixels=1_000_000):
    check_preview_budget(session.size)
    return build_source_maps(session._render_source(change, include_nbt=False, include_entities=False), assets, max_pixels)


def build_source_maps(source, assets=None, max_pixels=1_000_000, *, progress=None):
    from structura_render.mesh import face_texture_key, voxel_state
    from structura_render.projections import VIEWS as AXES, block_color, orient

    check_preview_budget(source.size)
    pixels = sum(math.prod(plane_size(source.size, view)) for view in VIEWS)
    if pixels > max_pixels:
        raise ValueError("Map projections exceed the pixel budget; reduce the loaded region")
    state, _, _, _ = voxel_state(source)
    scale = max(1, min(4, int(math.sqrt(max_pixels / max(1, pixels)))))
    bank = texture_bank(assets)
    faces = [bank.resolve(name) or {} for name in source.palette]
    background = np.array(ImageColor.getrgb(MAP_BACKGROUND), dtype=np.float32)
    result = {}
    for view in VIEWS:
        axis, reverse = AXES[view]
        data = np.moveaxis(state, axis, -1)
        if reverse:
            data = data[..., ::-1]
        direction = {"top": "up", "bottom": "down"}.get(view, view)
        tiles = []
        for name, textures in zip(source.palette, faces):
            image = textures.get(face_texture_key(direction, textures)) if textures else None
            if image is None:
                tile = np.full((scale, scale, 4), (*block_color(name, "family"), 1), dtype=np.float32)
            else:
                tile = np.array(image.convert("RGBA").resize((scale, scale), Image.Resampling.BOX), dtype=np.float32)
                tile[..., 3] /= 255
                tile[..., :3] *= tile[..., 3:4]
            tiles.append(tile)
        tiles.append(np.zeros((scale, scale, 4), dtype=np.float32))
        tiles = np.asarray(tiles)
        opaque = (tiles[..., 3] == 1).all(axis=(1, 2))[data]
        height = orient(np.where(opaque.any(axis=-1), data.shape[-1] - opaque.argmax(axis=-1), 0), view).astype(np.float32)
        dx = np.diff(height, axis=1, prepend=height[:, :1])
        dy = np.diff(height, axis=0, prepend=height[:1])
        shade = np.clip(1 + np.clip(dx, -3, 3) * 0.055 + np.clip(dy, -3, 3) * 0.035, 0.72, 1.2)
        colors, remaining = _composite(data, tiles)
        order = orient(np.arange(math.prod(data.shape[:2])).reshape(data.shape[:2]), view)
        image = colors[order] * shade[..., None, None, None] + remaining[order] * background
        height, width = order.shape
        image = image.transpose(0, 2, 1, 3, 4).reshape(height * scale, width * scale, 3)
        result[view] = np.ascontiguousarray(np.clip(image, 0, 255), dtype=np.uint8)
        if progress:
            progress("Projections", len(result), len(VIEWS))
    return result
