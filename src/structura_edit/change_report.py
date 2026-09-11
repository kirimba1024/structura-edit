from collections import Counter
from dataclasses import dataclass, replace
from math import floor

from .cell_data import detached_cell
from .changes_view import block_kind


@dataclass(frozen=True)
class ChangeReport:
    added: int
    removed: int
    replaced: int
    block_data: int
    removed_data: int
    entities: int
    resized: bool
    hidden: int
    heights: tuple = ()

    def for_height(self, height):
        hidden = 0 if height.mode == "all" else sum(count for y, count in self.heights
                                                  if y > height.y or (height.mode == "layer" and y < height.y))
        return replace(self, hidden=hidden)

    @property
    def summary(self):
        parts = [f"+{self.added:,} / −{self.removed:,} / ~{self.replaced:,} blocks"]
        if self.block_data:
            parts.append(f"{self.block_data:,} block data ({self.removed_data:,} removed)")
        if self.entities:
            parts.append(f"{self.entities:,} entities")
        if self.resized:
            parts.append("bounds change")
        if self.hidden:
            parts.append(f"{self.hidden:,} outside slice")
        return " · ".join(parts)


def report_change(session, change, height=None):
    counts = {"added": 0, "removed": 0, "changed": 0}
    data = removed = hidden = 0
    heights = Counter()
    source = session._document.source
    for delta in change.changes:
        heights[delta.position[1] + session.origin[1]] += 1
        counts[block_kind(delta.before, delta.after)] += 1
        before = detached_cell(source, delta.before, delta.position) if delta.before else None
        after = detached_cell(source, delta.after, delta.position)
        old = before.data.nbt if before and before.data else None
        new = after.data.nbt if after.data else None
        data += old != new
        removed += bool(old and not new)
        if height is not None and height.mode != "all":
            y = delta.position[1] + session.origin[1]
            hidden += y > height.y or (height.mode == "layer" and y < height.y)
    for delta in change.entities:
        record = (delta.after or delta.before).unpack()
        heights[floor(float(record["pos"][1]) + session.origin[1])] += 1
        if height is not None:
            hidden += not height.includes_entity(record, session)
    return ChangeReport(counts["added"], counts["removed"], counts["changed"], data, removed,
                        len(change.entities), bool(change.resize), hidden, tuple(sorted(heights.items())))
