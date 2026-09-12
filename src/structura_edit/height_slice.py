from dataclasses import dataclass


@dataclass(frozen=True)
class HeightSlice:
    mode: str = "all"
    y: int = 0

    def __post_init__(self):
        if self.mode not in ("all", "below", "layer"):
            raise ValueError("Height mode must be all, below or layer")
        if not isinstance(self.y, int):
            raise ValueError("Height must be an integer")

    @property
    def label(self):
        return "All heights" if self.mode == "all" else f"Hide above {self.y}" if self.mode == "below" else f"Layer {self.y} only"

    def interval(self, session):
        height = session.size[1]
        if self.mode == "all":
            return 0, height
        y = self.y - session.origin[1]
        return (max(0, min(height, y)) if self.mode == "layer" else 0,
                max(0, min(height, y + 1)))

    def includes_entity(self, record, session):
        if self.mode == "all":
            return True
        y = float(record["pos"][1]) + session.origin[1]
        return y < self.y + 1 and (self.mode == "below" or y >= self.y)


def slice_sections(keys, before, after, size, chunk_size, origin=(0, 0, 0)):
    def covered(interval, key):
        start, stop = key[1] * chunk_size - origin[1], (key[1] + 1) * chunk_size - origin[1]
        if max(interval[0], start) >= min(interval[1], stop):
            return None
        lo = max(interval[0], start - 1)
        hi = min(interval[1], stop + 1, size[1])
        return (lo, hi) if lo < hi else None

    return {key for key in keys if covered(before, key) != covered(after, key)}
