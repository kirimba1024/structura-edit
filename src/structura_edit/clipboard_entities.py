from dataclasses import replace

from .changes import EntityDelta
from .entity_data import EntityData, entity_key
from .entity_transform import new_identity
from structura_core.entity_grid_transform import transform_entity


def capture_entities(edit, selection):
    entities, players = [], 0
    offset = tuple(-v for v in selection.lower)
    for key, data in edit._entities.items():
        record = data.unpack()
        if tuple(float(v) for v in record["pos"]) not in selection:
            continue
        if (data.location is not None and data.location.storage == "player") or str(record["nbt"].get("id", "")) == "minecraft:player":
            players += 1
            continue
        entities.append((key, data.shifted(offset)))
    return tuple(entities), players


def transform_entities(entities, size, transform):
    return tuple((key, replace(data, record=transform_entity(data.unpack(), size, transform).to_snbt()))
                 for key, data in entities)


def place_entities(edit, clipboard, positions, *, take):
    changes = []
    for position in positions:
        for key, data in clipboard.entities:
            after = data.shifted(position)
            if take:
                before = edit._entities[key]
                after = replace(after, location=before.location)
            else:
                record = after.unpack()
                new_identity(record["nbt"])
                key, before = entity_key(record), None
                after = EntityData(record.to_snbt())
            if after != before:
                changes.append(EntityDelta(key, before, after))
    return tuple(changes)
