from .changes import Selection, _position


class RegionSelection:
    def __init__(self):
        self.size = (1, 1, 1)
        self.region = None
        self.anchor = None
        self.preview = None
        self.extending = False

    def reset(self, size):
        self.size = tuple(size)
        self.clear()

    def clear(self):
        self.region = None
        self.anchor = None
        self.preview = None
        self.extending = False

    def set_bounds(self, lower, upper):
        region = Selection(lower, upper)
        if any(hi > size for hi, size in zip(region.upper, self.size)):
            raise ValueError("Outside document bounds")
        self.region = region
        self.anchor = region.lower
        self.preview = None
        self.extending = False

    @property
    def opposite(self):
        if self.region is None:
            return None
        return tuple(hi - 1 if anchor == lo else lo
                     for anchor, lo, hi in zip(self.anchor, self.region.lower, self.region.upper))

    def set_corner(self, index, position):
        if index not in (0, 1):
            raise ValueError("Choose corner A or B")
        position = _position(position)
        first = position if index == 0 or self.anchor is None else self.anchor
        second = position if index == 1 or self.opposite is None else self.opposite
        region = Selection.from_corners(first, second)
        self.set_bounds(region.lower, region.upper)
        self.anchor = first

    def select_block(self, position, *, extend=False):
        anchor = self.anchor if extend and self.anchor is not None else position
        region = Selection.from_corners(anchor, position)
        self.set_bounds(region.lower, region.upper)
        self.anchor = _position(anchor)

    def adjusted(self, mode, value):
        if self.region is None:
            raise ValueError("Select a region first")
        if mode == "grow":
            region = self.region.expanded(value)
        elif mode == "shift":
            region = self.region.shifted(value)
        else:
            raise ValueError("Unknown selection adjustment")
        if any(hi > size for hi, size in zip(region.upper, self.size)):
            raise ValueError("Outside document bounds")
        return region

    def adjust(self, mode, value):
        region = self.adjusted(mode, value)
        anchor = tuple(lo if a == old_lo else hi - 1
                       for a, old_lo, lo, hi in zip(self.anchor, self.region.lower, region.lower, region.upper))
        self.set_bounds(region.lower, region.upper)
        self.anchor = anchor

    def select_all(self):
        self.set_bounds((0, 0, 0), self.size)

    def set_extending(self, enabled):
        self.extending = bool(enabled and self.anchor is not None)
        self.preview = None

    def hover_block(self, position):
        if not self.extending:
            return
        self.preview = Selection.from_corners(self.anchor, position)
