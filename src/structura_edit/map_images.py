import math

import numpy as np
from PIL import Image, ImageColor

from .appearance import MAP_BACKGROUND
from .loading import MAX_COLUMN_CELLS, check_preview_budget
from .map_projection import VIEWS, cave_view, plane_size, slice_bounds
from .resources import texture_bank


MAP_RENDER_VERSION = 6
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
        pending = active
        while pending.size:
            row, column = np.divmod(pending, data.shape[1])
            pending = pending[~occupied[row, column, depth[pending]]]
            depth[pending] += 1
            pending = pending[depth[pending] < data.shape[-1]]
        active = active[depth[active] < data.shape[-1]]
    return colors, remaining


def build_maps(session, change=None, assets=None, max_pixels=MAX_MAP_PIXELS):
    check_preview_budget(session.size, world=hasattr(session, "dimension"))
    return build_source_maps(session._render_source(change, include_nbt=False, include_entities=False), assets, max_pixels)


def build_source_maps(source, assets=None, max_pixels=MAX_MAP_PIXELS, *, progress=None, cut=None):
    return MapRenderer(source, assets).images(cut=cut, max_pixels=max_pixels, progress=progress)


def map_faces(source, bank):
    from structura_render.block_model import particle_texture
    from structura_render.textures import tint_for

    faces = []
    with bank.context.activate():
        for name, raw in zip(source.palette, source.palette_raw):
            textures = bank.resolve(name)
            if not textures:
                props = {key: str(value) for key, value in raw.get('Properties', {}).items()}
                texture = particle_texture(name, props)
                image = bank.read_texture(texture, tint_for(name, props)) if texture else None
                textures = {'all': image} if image is not None else {}
            faces.append(textures)
    return faces


class MapRenderer:
    def __init__(self, source, assets=None):
        from structura_render.mesh import voxel_state

        world = getattr(source, "world", False)
        check_preview_budget(source.size, world=world)
        self.size = source.size
        self.state, _, _, _ = voxel_state(source, **({"max_voxels": MAX_COLUMN_CELLS} if world else {}))
        self.palette = source.palette
        self.faces = map_faces(source, texture_bank(assets))
        self.tiles = {}
        self.detail_tiles = {}
        self.rendered = {}
        self._environment = None

    @property
    def environment(self):
        from .map_environment import MapEnvironment

        if self._environment is None:
            self._environment = MapEnvironment(self.state, self.palette)
        return self._environment

    def images(self, *, cut=None, max_pixels=MAX_MAP_PIXELS, progress=None, cave_y=None, views=VIEWS):
        pixels = sum(math.prod(plane_size(self.size, view)) for view in views)
        if pixels > max_pixels:
            raise ValueError("Map projections exceed the pixel budget; reduce the loaded region")
        scale = max(1, min(MAP_TEXTURE_SIZE, int(math.sqrt(max_pixels / max(1, pixels)))))
        images = {}
        for view in views:
            cave = cave_view(view, cut, cave_y)
            bounds = slice_bounds(self.size, cut, view)
            key = scale, bounds, cave_y if cave else None
            if view not in self.rendered or self.rendered[view][0] != key:
                cached = self.tiles.get(view)
                if cached is None or cached[0] != (scale, cave):
                    tiles = map_tiles(self.palette, self.faces, "top" if cave else view, scale)
                    self.tiles[view] = (scale, cave), tiles
                else:
                    tiles = cached[1]
                if cave:
                    state, heights = self.environment.floor(cave_y)
                    pixels = render_map(state, "top", (0, 1), tiles, heights=heights)
                else:
                    pixels = render_map(self.state, view, bounds, tiles)
                self.rendered[view] = key, pixels
            images[view] = self.rendered[view][1]
            if progress:
                progress("Projections", len(images), len(views))
        return images

    def details(self, areas, *, cut=None, cave_y=None):
        result = {}
        for view, area in areas:
            cave = cave_view(view, cut, cave_y)
            key = view, cave
            if key not in self.detail_tiles:
                self.detail_tiles[key] = map_tiles(self.palette, self.faces, "top" if cave else view, MAP_TEXTURE_SIZE)
            if cave:
                state, heights = self.environment.floor(cave_y)
                pixels = render_map(state, "top", (0, 1), self.detail_tiles[key], area=area, heights=heights)
            else:
                pixels = render_map(self.state, view, slice_bounds(self.size, cut, view), self.detail_tiles[key], area=area)
            result[view] = area, pixels
        return result


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


def projection_data(state, view, bounds):
    from structura_render.projection_grid import VIEWS as AXES

    axis, reverse = AXES[view]
    data = np.moveaxis(state, axis, -1)[..., bounds[0]:bounds[1]]
    if reverse:
        data = data[..., ::-1]
    if view in ("top", "bottom", "north", "south"):
        data = data.swapaxes(0, 1)
    if view in ("north", "south", "west", "east"):
        data = data[::-1]
    if view in ("south", "east"):
        data = data[:, ::-1]
    return data


def render_map(state, view, bounds, tiles, *, area=None, heights=None):
    data = projection_data(state, view, bounds)
    if area is not None:
        x0, y0, x1, y1 = area
        left, top = max(0, x0 - 1), max(0, y0 - 1)
        data = data[top:y1, left:x1]
        if heights is not None:
            heights = heights[top:y1, left:x1]
    opaque = (tiles[..., 3] == 1).all(axis=(1, 2))[data]
    depth = np.where(opaque.any(axis=-1), data.shape[-1] - opaque.argmax(axis=-1), 0) if data.shape[-1] else np.zeros(data.shape[:2])
    height = (depth if heights is None else heights).astype(np.float32)
    dx = np.diff(height, axis=1, prepend=height[:, :1])
    dy = np.diff(height, axis=0, prepend=height[:1])
    shade = np.clip(1 + np.clip(dx, -3, 3) * 0.055 + np.clip(dy, -3, 3) * 0.035, 0.72, 1.2)
    colors, remaining = _composite(data, tiles)
    height, width = data.shape[:2]
    colors = colors.reshape(height, width, *colors.shape[1:])
    remaining = remaining.reshape(height, width, *remaining.shape[1:])
    background = np.array(ImageColor.getrgb(MAP_BACKGROUND), dtype=np.float32)
    image = colors * shade[..., None, None, None] + remaining * background
    scale = tiles.shape[1]
    image = image.transpose(0, 2, 1, 3, 4).reshape(height * scale, width * scale, 3)
    if area is not None:
        image = image[(y0 - top) * scale:, (x0 - left) * scale:]
    return np.ascontiguousarray(np.clip(image, 0, 255), dtype=np.uint8)
