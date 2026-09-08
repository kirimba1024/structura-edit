from math import floor, prod


CHUNK_SIZE = 16
DEFAULT_RADIUS = 1
DEFAULT_VERTICAL_RADIUS = 32
MAX_WORLD_CELLS = 2_000_000
MAX_WORLD_BLOCKS = 750_000
MAX_PENDING_BLOCKS = 500_000
MAX_PREVIEW_CELLS = 8_000_000
MAX_GEOMETRY_BYTES = 192 * 1024**2
MAP_TILE_SIZE = 128
MAX_MAP_VISIBLE_TILES = 192


def region_bounds(center, radius, vertical_radius):
    x, y, z = center
    lower = ((floor(x / CHUNK_SIZE) - radius) * CHUNK_SIZE,
             floor((y - vertical_radius) / CHUNK_SIZE) * CHUNK_SIZE,
             (floor(z / CHUNK_SIZE) - radius) * CHUNK_SIZE)
    width = (2 * radius + 1) * CHUNK_SIZE
    upper = (lower[0] + width, (floor((y + vertical_radius) / CHUNK_SIZE) + 1) * CHUNK_SIZE,
             lower[2] + width)
    return lower, upper


def check_world_budget(center, radius, vertical_radius):
    lower, upper = region_bounds(center, radius, vertical_radius)
    volume = prod(hi - lo for lo, hi in zip(lower, upper))
    if volume > MAX_WORLD_CELLS:
        raise ValueError(f"World view needs {volume:,} cells; the editor limit is {MAX_WORLD_CELLS:,}. Reduce the radius.")


def check_preview_budget(size):
    if prod(size) > MAX_PREVIEW_CELLS:
        raise ValueError("Preview exceeds 8 million cells; split the schematic or reduce the world radius")


def geometry_bytes(data):
    arrays = {id(array): array.nbytes for geometry in data["meshes"] for array in
              (geometry.points, geometry.quads, geometry.uv, geometry.alpha_modes, geometry.image)}
    arrays.update((id(array), array.nbytes) for points, faces, color in data["flat"] for array in (points, faces))
    return sum(arrays.values())


def replacement_sizes(data, retained):
    sizes = {} if data["reset"] else retained.copy()
    sizes.update((key, section["geometry_bytes"]) for key, section in data["sections"].items())
    if sum(sizes.values()) > MAX_GEOMETRY_BYTES:
        raise ValueError("Scene geometry exceeds 192 MiB; reduce the loaded area or schematic size")
    return sizes
