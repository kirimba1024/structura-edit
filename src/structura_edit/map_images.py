import math

import numpy as np
from PIL import Image, ImageColor

from .appearance import MAP_BACKGROUND
from .loading import check_preview_budget
from .map_projection import VIEWS, plane_size, slice_bounds
from .resources import texture_bank


MAP_RENDER_VERSION = 4
MAP_TEXTURE_SIZE = 16
MAX_MAP_PIXELS = 8_000_000


def _composite(data, tiles):
    if data.shape[-1] == 0:
        shape = (math.prod(data.shape[:2]), *tiles.shape[1:3])
        return np.zeros((*shape, 3), dtype=np.float32), np.ones((*shape, 1), dtype=np.float32)
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


def build_maps(session, change=None, assets=None, max_pixels=MAX_MAP_PIXELS):
    check_preview_budget(session.size)
    return build_source_maps(session._render_source(change, include_nbt=False, include_entities=False), assets, max_pixels)


def build_source_maps(source, assets=None, max_pixels=MAX_MAP_PIXELS, *, progress=None, cut=None):
    return MapRenderer(source, assets).images(cut=cut, max_pixels=max_pixels, progress=progress)


class MapRenderer:
    def __init__(self, source, assets=None):
        from structura_render.mesh import voxel_state

        check_preview_budget(source.size)
        self.size = source.size
        self.state, _, _, _ = voxel_state(source)
        self.palette = source.palette
        bank = texture_bank(assets)
        self.faces = [bank.resolve(name) or {} for name in source.palette]
        self.tiles = {}
        self.rendered = {}

    def images(self, *, cut=None, max_pixels=MAX_MAP_PIXELS, progress=None):
        pixels = sum(math.prod(plane_size(self.size, view)) for view in VIEWS)
        if pixels > max_pixels:
            raise ValueError("Map projections exceed the pixel budget; reduce the loaded region")
        scale = max(1, min(MAP_TEXTURE_SIZE, int(math.sqrt(max_pixels / max(1, pixels)))))
        images = {}
        for view in VIEWS:
            bounds = slice_bounds(self.size, cut, view)
            key = scale, bounds
            if view not in self.rendered or self.rendered[view][0] != key:
                cached = self.tiles.get(view)
                if cached is None or cached[0] != scale:
                    tiles = map_tiles(self.palette, self.faces, view, scale)
                    self.tiles[view] = scale, tiles
                else:
                    tiles = cached[1]
                self.rendered[view] = key, render_map(self.state, view, bounds, tiles)
            images[view] = self.rendered[view][1]
            if progress:
                progress("Projections", len(images), len(VIEWS))
        return images


def map_tiles(palette, faces, view, scale):
    from structura_render.atlas import face_texture_key
    from structura_render.block_colours import block_color

    direction = {"top": "up", "bottom": "down"}.get(view, view)
    tiles = []
    for name, textures in zip(palette, faces):
        image = textures.get(face_texture_key(direction, textures)) if textures else None
        if image is None:
            tile = np.full((scale, scale, 4), (*block_color(name, "family"), 1), dtype=np.float32)
        else:
            tile = np.array(image.convert("RGBA").resize((scale, scale), Image.Resampling.BOX), dtype=np.float32)
            tile[..., 3] /= 255
            tile[..., :3] *= tile[..., 3:4]
        tiles.append(tile)
    tiles.append(np.zeros((scale, scale, 4), dtype=np.float32))
    return np.asarray(tiles)


def render_map(state, view, bounds, tiles):
    from structura_render.projection_grid import VIEWS as AXES, orient

    axis, reverse = AXES[view]
    data = np.moveaxis(state, axis, -1)[..., bounds[0]:bounds[1]]
    if reverse:
        data = data[..., ::-1]
    opaque = (tiles[..., 3] == 1).all(axis=(1, 2))[data]
    depth = np.where(opaque.any(axis=-1), data.shape[-1] - opaque.argmax(axis=-1), 0) if data.shape[-1] else np.zeros(data.shape[:2])
    height = orient(depth, view).astype(np.float32)
    dx = np.diff(height, axis=1, prepend=height[:, :1])
    dy = np.diff(height, axis=0, prepend=height[:1])
    shade = np.clip(1 + np.clip(dx, -3, 3) * 0.055 + np.clip(dy, -3, 3) * 0.035, 0.72, 1.2)
    colors, remaining = _composite(data, tiles)
    order = orient(np.arange(math.prod(data.shape[:2])).reshape(data.shape[:2]), view)
    background = np.array(ImageColor.getrgb(MAP_BACKGROUND), dtype=np.float32)
    image = colors[order] * shade[..., None, None, None] + remaining[order] * background
    height, width = order.shape
    scale = tiles.shape[1]
    image = image.transpose(0, 2, 1, 3, 4).reshape(height * scale, width * scale, 3)
    return np.ascontiguousarray(np.clip(image, 0, 255), dtype=np.uint8)
