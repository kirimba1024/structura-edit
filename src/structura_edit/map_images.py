import math

import numpy as np
from PIL import Image, ImageColor

from .appearance import MAP_BACKGROUND
from .loading import check_preview_budget
from .map_projection import VIEWS, plane_size
from .resources import texture_bank


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
        occupied = data >= 0
        depth = occupied.argmax(axis=-1)
        visible = np.take_along_axis(data, depth[..., None], axis=-1)[..., 0]
        present = orient(occupied.any(axis=-1), view)
        visible = orient(visible, view)
        height = orient(data.shape[-1] - depth, view).astype(np.float32)
        dx = np.diff(height, axis=1, prepend=height[:, :1])
        dy = np.diff(height, axis=0, prepend=height[:1])
        shade = np.clip(1 + np.clip(dx, -3, 3) * 0.055 + np.clip(dy, -3, 3) * 0.035, 0.72, 1.2)
        direction = {"top": "up", "bottom": "down"}.get(view, view)
        tiles = []
        for name, textures in zip(source.palette, faces):
            image = textures.get(face_texture_key(direction, textures)) if textures else None
            if image is None:
                tile = np.full((scale, scale, 3), block_color(name, "family"), dtype=np.float32)
            else:
                values = np.asarray(image.convert("RGBA").resize((scale, scale), Image.Resampling.BOX), dtype=np.float32)
                alpha = values[:, :, 3:4] / 255
                tile = values[:, :, :3] * alpha + background * (1 - alpha)
            tiles.append(tile)
        tiles = np.asarray(tiles)
        height, width = visible.shape
        image = tiles[np.maximum(visible, 0)].transpose(0, 2, 1, 3, 4).reshape(height * scale, width * scale, 3)
        image *= np.repeat(np.repeat(shade, scale, axis=0), scale, axis=1)[:, :, None]
        image[~np.repeat(np.repeat(present, scale, axis=0), scale, axis=1)] = background
        result[view] = np.ascontiguousarray(np.clip(image, 0, 255), dtype=np.uint8)
        if progress:
            progress("Projections", len(result), len(VIEWS))
    return result
