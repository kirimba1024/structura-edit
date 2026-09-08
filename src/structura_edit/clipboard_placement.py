from dataclasses import dataclass, replace
from itertools import product
from math import floor, prod
from numbers import Integral

from .cell_data import detached_cell
from .changes import ChangeSet, StaleChangeError, _Cell, _Delta, _position
from .document_resize import placement_extent
from .destination_rule import DestinationRule
from .clipboard_entities import place_entities
from .picking import EMPTY


def source_cells(edit, clipboard):
    for local, cell in clipboard.cells:
        if clipboard.document_id != edit._id or clipboard.dimension != getattr(edit, "dimension", None):
            yield local, replace(cell, variant=None, origin=None)
            continue
        if cell.origin is not None:
            origin = tuple(p + old - new for p, old, new in zip(cell.origin, clipboard.origin, edit.origin))
            original = edit._original(origin)
            if original is None or original.variant != cell.variant:
                cell = replace(cell, variant=None, origin=None)
            else:
                cell = replace(cell, origin=origin)
                candidate = replace(cell, data=None)
                if detached_cell(edit._document.source, candidate, origin).data == cell.data:
                    cell = candidate
        yield local, cell


@dataclass(frozen=True)
class PlacementPlan:
    change: ChangeSet
    matched: int
    skipped: int

    @property
    def summary(self):
        changed = len(self.change.changes)
        if self.change.entities:
            summary = f"{changed:,} blocks · {len(self.change.entities):,} entities"
            return summary + (f" · {self.skipped:,} skipped" if self.skipped else "")
        return f"{changed:,} changed · {self.skipped:,} skipped" if changed else f"No changes · {self.skipped:,} skipped"


def check_destination(edit, position):
    if not hasattr(edit, "world_changes"):
        return
    x, y, z = (p + o for p, o in zip(position, edit.origin))
    if (x // 16, z // 16) not in edit.loaded_chunks:
        raise ValueError("Placement includes absent chunks; select a loaded area")
    if edit.loaded_sections is not None and (x // 16, y // 16, z // 16) not in edit.loaded_sections:
        raise ValueError("Placement includes an absent section; stay within the world's existing build height")


def filter_destinations(edit, targets, rule):
    if rule.mode == "all":
        if hasattr(edit, "world_changes"):
            for position in targets:
                check_destination(edit, position)
        return targets, 0
    accepted, allowed_states = {}, {}
    for position, cell in targets.items():
        check_destination(edit, position)
        before = edit._cell(position)
        state = before.state if before else None
        if state not in allowed_states:
            allowed_states[state] = rule.allows(state)
        if allowed_states[state]:
            accepted[position] = cell
    return accepted, len(targets) - len(accepted)


def protect_skipped_sources(clipboard, cells, position, accepted):
    sources = dict(zip((local for local, _ in clipboard.cells), clipboard.sources))
    incoming = {tuple(p + d for p, d in zip(local, position)): sources[local] for local, cell in cells
                if cell.state.split("[", 1)[0] not in EMPTY}
    protected = [source for target, source in incoming.items() if target not in accepted]
    skipped = 0
    while protected:
        source = protected.pop()
        if source in accepted:
            del accepted[source]
            skipped += 1
            if source in incoming:
                protected.append(incoming[source])
    return skipped


def plan_placement(edit, clipboard, positions, *, take=False, include_air=False, include_blocks=True, include_entities=True,
                   destination=DestinationRule(), label="Paste"):
    if edit.readonly:
        raise ValueError("This source is view-only in this release")
    if not include_blocks and not include_entities:
        raise ValueError("Choose Blocks or Entities to place")
    work = (prod(clipboard.size) if include_blocks else 0) + (len(clipboard.entities) if include_entities else 0)
    if not positions or len(positions) * work > edit.operation_limit:
        raise ValueError("Placement exceeds the object budget")
    if take and len(positions) != 1:
        raise ValueError("Take places one copy at a time")
    if take and not clipboard.can_take_from(edit):
        raise StaleChangeError("The source changed; take a fresh selection")
    lower = tuple(min(p[axis] for p in positions) for axis in range(3))
    upper = tuple(max(p[axis] for p in positions) + size for axis, size in enumerate(clipboard.size))
    resize = placement_extent(edit, lower, tuple(hi - lo for lo, hi in zip(lower, upper)))
    cells = tuple((p, cell) for p, cell in (source_cells(edit, clipboard) if include_blocks else ())
                  if include_air or cell.state.split("[", 1)[0] not in EMPTY)
    targets = {}
    for position in positions:
        if include_blocks and include_air:
            targets.update((p, _Cell("minecraft:air")) for p in product(
                *(range(lo, lo + size) for lo, size in zip(position, clipboard.size))))
        targets.update((tuple(p + d for p, d in zip(local, position)), cell) for local, cell in cells)
    accepted, skipped = filter_destinations(edit, targets, destination)
    if take and skipped:
        skipped += protect_skipped_sources(clipboard, cells, positions[0], accepted)
    entities = place_entities(edit, clipboard, positions, take=take) if include_entities else ()
    if entities or destination.mode != "all" or not include_blocks:
        footprint = list(accepted) if destination.mode != "all" or not include_blocks else [lower, tuple(v - 1 for v in upper)]
        occupied = footprint + [tuple(floor(float(v)) for v in delta.after.unpack()["pos"]) for delta in entities]
        lower = tuple(min(p[axis] for p in occupied) for axis in range(3)) if occupied else None
        size = tuple(max(p[axis] for p in occupied) - lower[axis] + 1 for axis in range(3)) if occupied else None
        resize = placement_extent(edit, lower, size) if occupied else None
    if take:
        targets = {}
        sources = dict(zip((local for local, _ in clipboard.cells), clipboard.sources))
        for local, cell in cells:
            if cell.state.split("[", 1)[0] not in EMPTY and any(
                    tuple(p + d for p, d in zip(local, destination_position)) in accepted for destination_position in positions):
                targets[sources[local]] = _Cell("minecraft:air")
        targets.update(accepted)
    else:
        targets = accepted
    changes = []
    for position, cell in targets.items():
        before = edit._cell(position)
        if before != cell:
            changes.append(_Delta(position, before, cell))
    change = ChangeSet(edit._id, edit.revision, label, tuple(changes), entities, resize)
    edit._check_change(change)
    return PlacementPlan(change, len(accepted), skipped)


def plan_stack(edit, selection, copies, step, *, include_air=False, include_blocks=True, include_entities=True, destination=DestinationRule()):
    edit._check_readable(selection)
    if isinstance(copies, bool) or not isinstance(copies, Integral) or copies < 1:
        raise ValueError("Copies must be a positive integer")
    if include_blocks and copies * selection.volume > edit.operation_limit:
        raise ValueError("Stack exceeds the cell budget; reduce copies or selection")
    step = _position(step)
    if not any(step):
        raise ValueError("Choose a nonzero step for Stack")
    if copies > edit.operation_limit:
        raise ValueError("Stack exceeds the copy budget")
    clipboard = edit.copy(selection, include_blocks=include_blocks, include_entities=include_entities)
    if copies * len(clipboard.entities) > edit.operation_limit:
        raise ValueError("Stack exceeds the entity budget")
    positions = tuple(tuple(p + count * d for p, d in zip(selection.lower, step)) for count in range(1, copies + 1))
    return plan_placement(edit, clipboard, positions, include_air=include_air, include_blocks=include_blocks,
                          include_entities=include_entities, destination=destination, label=f"Stack {copies} copies")
