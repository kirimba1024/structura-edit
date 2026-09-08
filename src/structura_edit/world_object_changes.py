from dataclasses import replace
from math import floor

from structura_core.world_entities import EntityLocation
from structura_core.world_entity_write import EntityPatch

from .changes import EntityDelta
from .entity_data import entity_key, initial_entities


def loaded_entities(session, locations):
    base = initial_entities(session._document.source, locations)
    return {entity_key(data.shifted(session.origin).unpack()) if data.location is not None else key: data
            for key, data in base.items()}


def visible_entities(session):
    entities = session._base_entities.copy()
    by_record = {data.shifted(session.origin).record: key for key, data in entities.items()}
    for key, (before, after) in session.world_changes.entities.items():
        entities.pop(key, None)
        for value in (before, after):
            if value is not None:
                entities.pop(by_record.get(value.record), None)
        if after is None or after.location.dimension != session.dimension:
            continue
        local = after.shifted(tuple(-v for v in session.origin))
        position = tuple(float(v) for v in local.unpack()["pos"])
        if all(0 <= v < size for v, size in zip(position, session.size)):
            entities[key] = local
    return entities


def portable_entities(session, changes):
    def portable(data):
        if data is None:
            return None
        result = data.shifted(session.origin)
        location = result.location
        if location is None:
            location = EntityLocation(session.dimension, "entities")
        if location.storage != "player":
            x, _, z = (float(v) for v in result.unpack()["pos"])
            location = replace(location, chunk=(floor(x / 16), floor(z / 16)))
        return replace(result, location=location)

    return tuple(EntityDelta(delta.key, portable(delta.before), portable(delta.after)) for delta in changes)


def entity_patches(changes):
    def payload(data):
        if data is None:
            return None
        record = data.unpack()
        result = record["nbt"]
        result["Pos"] = record["pos"]
        return result.to_snbt()

    return tuple(EntityPatch(before.location if before else None, payload(before),
                             after.location if after else None, payload(after))
                 for before, after in changes.entities.values())
