from dataclasses import dataclass
from math import ceil, floor, radians, sqrt, tan
import heapq


TILE_SPAN = 16
DETAIL_BUDGET = 96 * 1024**2
STAGING_BUDGET = DETAIL_BUDGET
SELECTION_BUDGET = 88 * 1024**2
SETTLE_MILLISECONDS = 350
PIXEL_ERROR = 1.5


def parent_key(key):
    level, x, y, z = key
    return level + 1, x // 2, y // 2, z // 2


def tile_bounds(key):
    level, *position = key
    span = TILE_SPAN * 2**level
    lower = tuple(p * span for p in position)
    return lower, tuple(p + span for p in lower)


def intersects(first, second):
    return all(a < d and c < b for a, b, c, d in zip(first[0], first[1], second[0], second[1]))


def contains(outer, inner):
    return all(a <= c and d <= b for a, b, c, d in zip(outer[0], outer[1], inner[0], inner[1]))


@dataclass(frozen=True)
class OverviewNode:
    key: tuple
    children: tuple
    error: float
    nbytes: int


@dataclass(frozen=True)
class DetailTarget:
    cell: tuple
    pixels: int
    fov: float
    excluded: tuple = ()

    @classmethod
    def at(cls, position, pixels, fov, excluded=()):
        return cls(tuple(floor(p / TILE_SPAN) for p in position), max(64, ceil(pixels / 64) * 64),
                   float(fov), excluded)

    def error_pixels(self, node):
        view_lower, view_upper = tile_bounds((0, *self.cell))
        lower, upper = tile_bounds(node.key)
        distance = sqrt(sum(max(a - d, c - b, 0)**2
                            for a, b, c, d in zip(view_lower, view_upper, lower, upper)))
        scale = self.pixels / (2 * tan(radians(self.fov) / 2))
        return node.error * scale / max(distance, 0.01)


def select_detail(nodes, roots, target, budget=SELECTION_BUDGET, pixel_error=PIXEL_ERROR):
    if not 1 <= target.fov < 179:
        raise ValueError("Field of view must be between 1 and 179 degrees")
    selected = set()

    def include(key):
        node = nodes[key]
        bounds = tile_bounds(key)
        if target.excluded and intersects(bounds, target.excluded):
            if contains(target.excluded, bounds):
                return
            if node.children:
                for child in node.children:
                    include(child)
                return
            raise ValueError("Editing bounds must follow the snapshot tile grid")
        selected.add(key)

    for key in sorted(roots):
        include(key)
    size = sum(nodes[key].nbytes for key in selected)
    if size > budget:
        raise ValueError("Overview coverage exceeds the memory budget; reduce the world overview size")
    queue = []

    def request(key):
        node = nodes[key]
        error = target.error_pixels(node)
        if node.children and error > pixel_error:
            heapq.heappush(queue, (-error, key))

    for key in sorted(selected):
        request(key)
    while queue:
        _, key = heapq.heappop(queue)
        node = nodes[key]
        replacement = sum(nodes[child].nbytes for child in node.children)
        if size - node.nbytes + replacement > budget:
            continue
        selected.remove(key)
        selected.update(node.children)
        size += replacement - node.nbytes
        for child in node.children:
            request(child)
    return tuple(sorted(selected))


class DetailIntent:
    def __init__(self):
        self.generation = 0
        self.target = None
        self.destination = None

    def request(self, target, destination=None):
        if (target, destination) != (self.target, self.destination):
            self.generation += 1
            self.target, self.destination = target, destination
        return self.generation

    def cancel(self):
        self.generation += 1
        self.target = self.destination = None

    def accepts(self, generation):
        return self.target is not None and generation == self.generation
