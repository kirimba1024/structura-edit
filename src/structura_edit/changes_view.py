from .picking import EMPTY


OUTLINE_LIMIT = 100_000


def unsaved_changes(session):
    changed, added, removed = [], [], []
    for position, cell in session._cells.items():
        original = session._original(position)
        if original is None:
            added.append(position)
        elif cell is None or cell.state.split("[", 1)[0] in EMPTY:
            removed.append(position)
        else:
            changed.append(position)
    return {"changed": tuple(changed), "added": tuple(added), "removed": tuple(removed),
            "outlined": len(changed) + len(added) + len(removed) <= OUTLINE_LIMIT}


def summary(result):
    changed, added, removed = len(result["changed"]), len(result["added"]), len(result["removed"])
    text = f"{changed + added + removed:,} unsaved changes"
    if changed or added or removed:
        parts = [f"{count} {kind}" for count, kind in ((changed, "changed"), (added, "added"), (removed, "removed"))
                 if count]
        text = f"{text}: " + ", ".join(parts)
    return text + ("" if result["outlined"] else " · outline hidden, too many cells")
