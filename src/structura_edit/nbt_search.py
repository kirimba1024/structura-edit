from dataclasses import dataclass

from amulet_nbt import CompoundTag, StringTag

from .nbt_values import ARRAY_VALUES, CONTAINERS, INTEGER_BITS, path_text, value_summary


PAGE_SIZE = 128
MAX_FIELDS = 100_000
MAX_DEPTH = 128


@dataclass(frozen=True)
class NbtMatch:
    path: tuple
    columns: tuple
    count_path: object = None


@dataclass(frozen=True)
class NbtPage:
    rows: tuple
    total: int
    offset: int
    limited: bool


def item_fields(value):
    if not isinstance(value, CompoundTag):
        return None
    identity = value.get("id", value.get("Id"))
    count_key = "count" if "count" in value else "Count"
    count = value.get(count_key)
    if isinstance(identity, StringTag) and type(count) in INTEGER_BITS:
        return str(value.get("Slot", value.get("slot", "—"))), str(identity), str(count), count_key
    return None


def find_nbt(root, text="", *, items=False, offset=0, cancel=None):
    words = text[:256].casefold().replace("_", " ").split()
    offset = max(0, int(offset))
    pending = [iter([((), root)])]
    rows, visited, total, limited = [], 0, 0, False
    while pending:
        entry = next(pending[-1], None)
        if entry is None:
            pending.pop()
            continue
        if visited == MAX_FIELDS:
            limited = True
            break
        if visited % 128 == 0 and cancel is not None and cancel.is_set():
            return None
        path, value = entry
        visited += 1
        match = None
        fields = item_fields(value) if items else None
        if fields:
            slot, identity, count, count_key = fields
            match = NbtMatch(path, (slot, identity, count, path_text(path)), (*path, count_key))
        elif not items:
            match = NbtMatch(path, (path_text(path), type(value).__name__.removesuffix("Tag"), value_summary(value)))
        if match is not None:
            parts = (*match.columns[:2], str(value)) if not items and isinstance(value, StringTag) else match.columns
            content = " ".join(parts).casefold().replace("_", " ")
            if all(word in content for word in words):
                if offset <= total < offset + PAGE_SIZE:
                    rows.append(match)
                total += 1
        if isinstance(value, CONTAINERS) and len(value) and not (items and type(value) in ARRAY_VALUES):
            if len(path) >= MAX_DEPTH:
                limited = True
            else:
                pending.append(_children(path, value))
    return NbtPage(tuple(rows), total, offset, limited)


def _children(path, value):
    entries = value.items() if isinstance(value, CompoundTag) else enumerate(value)
    for key, child in entries:
        if type(value) in ARRAY_VALUES:
            child = ARRAY_VALUES[type(value)](int(child))
        yield (*path, key), child
