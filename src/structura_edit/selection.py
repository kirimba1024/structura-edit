from .session import Selection


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
            raise ValueError("Selection is outside the document")
        self.region = region
        self.anchor = region.lower
        self.preview = None
        self.extending = False

    def select_block(self, position, *, extend=False):
        anchor = self.anchor if extend and self.anchor is not None else position
        lower = tuple(min(a, p) for a, p in zip(anchor, position))
        upper = tuple(max(a, p) + 1 for a, p in zip(anchor, position))
        self.set_bounds(lower, upper)
        self.anchor = anchor

    def select_all(self):
        self.set_bounds((0, 0, 0), self.size)

    def set_extending(self, enabled):
        self.extending = bool(enabled and self.anchor is not None)
        self.preview = None

    def hover_block(self, position):
        if not self.extending:
            return
        lower = tuple(min(a, p) for a, p in zip(self.anchor, position))
        upper = tuple(max(a, p) + 1 for a, p in zip(self.anchor, position))
        self.preview = Selection(lower, upper)
