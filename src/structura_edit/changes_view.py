from .picking import EMPTY


OUTLINE_LIMIT = 100_000


def block_kind(before, after):
    old = before is not None and before.state.split("[", 1)[0] not in EMPTY
    new = after is not None and after.state.split("[", 1)[0] not in EMPTY
    return "added" if new and not old else "removed" if old and not new else "changed"


def unsaved_changes(session):
    positions = {kind: [] for kind in ("changed", "added", "removed")}
    counts = dict.fromkeys(positions, 0)
    world = getattr(session, "world_changes", None)
    state = world or session._saved_changes
    blocks = world.patch if world is not None else state.blocks
    outside, outlined = 0, 0
    for key, (before, after) in blocks.items():
        kind = block_kind(before, after)
        counts[kind] += 1
        point = key[1:] if world is not None else key
        local = tuple(p - o for p, o in zip(point, session.origin))
        visible = (world is None or key[0] == session.dimension) and all(0 <= p < s for p, s in zip(local, session.size))
        if visible and outlined < OUTLINE_LIMIT:
            positions[kind].append(local)
            outlined += 1
        outside += not visible
    resized = world is None and (state.origin != session.origin or state.size != session.size)
    return {**{kind: tuple(values) for kind, values in positions.items()}, "counts": counts,
            "entities": len(state.entities), "resized": resized, "outside": outside,
            "outlined": len(blocks) - outside <= OUTLINE_LIMIT}


def summary(result):
    counts = result["counts"]
    total = sum(counts.values()) + result["entities"] + bool(result["resized"])
    parts = [f"{count:,} {kind}" for kind, count in counts.items() if count]
    if result["entities"]:
        parts.append(f"{result['entities']:,} entities")
    if result["resized"]:
        parts.append("bounds changed")
    if result["outside"]:
        parts.append(f"{result['outside']:,} blocks outside document view")
    text = f"{total:,} unsaved changes" + (": " + ", ".join(parts) if parts else "")
    return text + ("" if result["outlined"] else " · outline hidden, too many cells")
