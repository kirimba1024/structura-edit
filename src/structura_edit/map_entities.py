from collections import OrderedDict

import numpy as np

from .map_projection import VIEWS, depth_axis, project
from .object_labels import entity_label
from .resources import texture_bank


APPEARANCE_FIELDS = ('id', 'variant', 'Variant', 'CatType', 'Type', 'RabbitType', 'Color', 'CustomName', 'IsBaby', 'Age')
_icons = OrderedDict()
_icon_bank = None


def entity_markers(records, assets):
    from structura_render.entity_icons import entity_icon

    global _icon_bank
    bank = texture_bank(assets)
    if bank is not _icon_bank:
        _icons.clear()
        _icon_bank = bank
    result = []
    with bank.context.activate():
        for record in records:
            nbt = record['nbt']
            kind = str(nbt.get('id', '')).removeprefix('minecraft:')
            key = tuple(str(nbt.get(field, '')) for field in APPEARANCE_FIELDS)
            if key not in _icons:
                _icons[key] = entity_icon(kind, nbt)
                if len(_icons) > 256:
                    _icons.popitem(last=False)
            _icons.move_to_end(key)
            result.append((tuple(float(v) for v in record['pos']), kind == 'player', entity_label(nbt), _icons[key]))
    return result


def icon_mode(mode, pixels_per_block, previous=False):
    return mode == 'Icons' or mode == 'Auto' and pixels_per_block >= (3 if previous else 4)


class MapMarkers:
    def __init__(self, positions):
        self.positions = np.asarray(positions, dtype=float).reshape(-1, 3)
        self.planes = {view: np.column_stack(project(self.positions.T, (0, 0, 0), view)) for view in VIEWS}

    def visible(self, view, origin, area, bounds, cave_y=None):
        points = self.planes[view]
        u, v = project(origin, (0, 0, 0), view)
        left, top, right, bottom = area
        mask = ((points[:, 0] >= left - u) & (points[:, 0] <= right - u)
                & (points[:, 1] >= top - v) & (points[:, 1] <= bottom - v))
        if view != "bottom":
            depth = self.positions[:, depth_axis(view)]
            mask &= (depth >= bounds[0]) & (depth < bounds[1])
        elif cave_y is not None:
            mask &= np.abs(self.positions[:, 1] - cave_y) <= 16
        indices = np.flatnonzero(mask)
        return indices, points[indices] + (u, v)
