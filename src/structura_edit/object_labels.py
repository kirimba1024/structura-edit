import json

from structura_render.signs import _plain_text


MAX_ENTITY_LABELS = 12


def entity_label(payload):
    value = str(payload.get("CustomName", ""))
    try:
        value = _plain_text(json.loads(value))
    except (ValueError, TypeError, RecursionError):
        pass
    value = " ".join(value.split())
    if not value:
        value = str(payload.get("id", "Entity")).split(":", 1)[-1].replace("_", " ").capitalize()
    return value[:39] + "…" if len(value) > 40 else value


def selected_labels(session, keys, bounds):
    labels = []
    for key in sorted(keys):
        if key not in bounds or key not in session._entities:
            continue
        lower, upper = bounds[key]
        position = ((lower[0] + upper[0]) / 2, upper[1] + 0.2, (lower[2] + upper[2]) / 2)
        labels.append((entity_label(session._entities[key].unpack()["nbt"]), position))
        if len(labels) == MAX_ENTITY_LABELS:
            break
    return tuple(labels)
