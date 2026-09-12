from math import ceil, floor

from .map_layout import projection_rect
from .map_projection import VIEWS, plane_size


def detail_areas(canvas):
    if not canvas.layout.large:
        return ()
    areas = []
    remaining = 8192
    views = (canvas.layout.focused,) if canvas.layout.focused else VIEWS
    for view in views:
        visible = canvas.layout.area(view)
        pixels = canvas.tile_rect(view).width() * canvas.devicePixelRatioF() / max(.001, visible.width())
        if pixels < 4:
            continue
        source = projection_rect(canvas.origin, canvas.size_blocks, view)
        visible = visible.intersected(source)
        if visible.isEmpty():
            continue
        width, height = plane_size(canvas.size_blocks, view)
        x0, y0 = max(0, floor(visible.left() - source.left())), max(0, floor(visible.top() - source.top()))
        x1, y1 = min(width, ceil(visible.right() - source.left())), min(height, ceil(visible.bottom() - source.top()))
        count = (x1 - x0) * (y1 - y0)
        if 0 < count <= remaining:
            areas.append((view, (x0, y0, x1, y1)))
            remaining -= count
    return tuple(areas)
