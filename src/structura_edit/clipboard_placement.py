from dataclasses import dataclass, replace
from itertools import product
from math import floor, prod
from numbers import Integral
from structura_core.compatibility import transfer_reason

from .cell_data import detached_cell
from .changes import AIR_CELL, ChangeSet, StaleChangeError, _Delta, _position
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
    reasons: tuple = ()
    entity_rule_notice: bool = False

    @property
    def summary(self):
        if self.change.report is not None:
            details = " · ".join(f"{count:,} skipped: {reason}" for reason, count in self.reasons if count)
            summary = self.change.report.summary + (" · " + details if details else "")
            return summary + (" · Entities are not filtered by block rules" if self.entity_rule_notice else "")
        changed = len(self.change.changes)
        if self.change.entities:
            summary = f"{changed:,} blocks · {len(self.change.entities):,} entities"
            return summary + (f" · {self.skipped:,} skipped" if self.skipped else "")
        return f"{changed:,} changed · {self.skipped:,} skipped" if changed else f"No changes · {self.skipped:,} skipped"


def filter_destinations(edit, targets, rule):
    if rule.mode == "all":
        for position in targets:
            edit._check_destination(position)
        return targets, 0
    accepted, allowed_states = {}, {}
    for position, cell in targets.items():
        edit._check_destination(position)
        before = edit._cell(position)
        state = before.state if before else None
        if rule.mode == "where":
            allowed = rule.condition.at(edit, position)
        else:
            if state not in allowed_states:
                allowed_states[state] = rule.allows(state)
            allowed = allowed_states[state]
        if allowed:
            accepted[position] = cell
    return accepted, len(targets) - len(accepted)


def take_targets(clipboard, cells, position, accepted):
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
    targets = {source: AIR_CELL for target, source in incoming.items() if target in accepted}
    targets.update(accepted)
    return targets, skipped


def _air_targets(clipboard, position):
    if clipboard.footprint is not None:
        return (tuple(p + d for p, d in zip(local, position)) for local in clipboard.footprint.positions())
    return product(*(range(lo, lo + size) for lo, size in zip(position, clipboard.size)))


def plan_placement(edit, clipboard, positions, *, take=False, include_air=False, include_blocks=True, include_entities=True,
                   destination=DestinationRule(), label="Paste"):
    if edit.readonly:
        raise ValueError("This source is view-only in this release")
    reason = transfer_reason(clipboard.data_version, edit._document.source.data_version)
    if reason:
        raise ValueError(reason)
    if not include_blocks and not include_entities:
        raise ValueError("Choose Blocks or Entities to place")
    work = 0
    if include_blocks:
        work = ((clipboard.footprint.volume if clipboard.footprint is not None else prod(clipboard.size))
                if include_air else clipboard.block_count)
    work += len(clipboard.entities) if include_entities else 0
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
            targets.update((p, AIR_CELL) for p in _air_targets(clipboard, position))
        targets.update((tuple(p + d for p, d in zip(local, position)), cell) for local, cell in cells)
    accepted, skipped = filter_destinations(edit, targets, destination)
    reasons = [("destination rule", skipped)]
    targets = accepted
    if take:
        targets, protected = take_targets(clipboard, cells, positions[0], accepted)
        skipped += protected
        reasons.append(("source overlap", protected))
    if include_entities and clipboard.excluded_players:
        reasons.append(("players remain in the source", clipboard.excluded_players))
    entities = place_entities(edit, clipboard, positions, take=take) if include_entities else ()
    if entities or destination.mode != "all" or not include_blocks:
        footprint = list(accepted) if destination.mode != "all" or not include_blocks else [lower, tuple(v - 1 for v in upper)]
        occupied = footprint + [tuple(floor(float(v)) for v in delta.after.unpack()["pos"]) for delta in entities]
        lower = tuple(min(p[axis] for p in occupied) for axis in range(3)) if occupied else None
        size = tuple(max(p[axis] for p in occupied) - lower[axis] + 1 for axis in range(3)) if occupied else None
        resize = placement_extent(edit, lower, size) if occupied else None
    changes = []
    for position, cell in targets.items():
        before = edit._cell(position)
        if before != cell:
            changes.append(_Delta(position, before, cell))
    change = ChangeSet(edit._id, edit.revision, label, tuple(changes), entities, resize)
    edit._check_change(change)
    return PlacementPlan(change, len(accepted), skipped, tuple(reasons), bool(entities and destination.mode != "all"))


def plan_stack(edit, selection, copies, step, *, include_air=False, include_blocks=True, include_entities=True, destination=DestinationRule()):
    edit._check_readable(selection)
    if isinstance(copies, bool) or not isinstance(copies, Integral) or copies < 1:
        raise ValueError("Copies must be a positive integer")
    if include_blocks and include_air and copies * selection.volume > edit.operation_limit:
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
