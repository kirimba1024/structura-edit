import numpy as np


BOX_CORNERS = np.array([(x, y, z) for x in (0, 1) for y in (0, 1) for z in (0, 1)])
BOX_EDGES = np.array([(index, index ^ bit) for index in range(8) for bit in (1, 2, 4) if index < (index ^ bit)])


def box_outlines(bounds):
    boxes = np.asarray(bounds, dtype=float).reshape(-1, 2, 3)
    points = boxes[:, 0, None] + (boxes[:, 1, None] - boxes[:, 0, None]) * BOX_CORNERS
    edges = BOX_EDGES[None] + (8 * np.arange(len(boxes)))[:, None, None]
    lines = np.full((len(boxes), 12, 3), 2, dtype=np.int64)
    lines[:, :, 1:] = edges
    return points.reshape(-1, 3), lines.ravel()
