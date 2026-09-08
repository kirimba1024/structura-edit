from dataclasses import dataclass
from hashlib import sha256
from math import floor
from typing import Optional

from amulet_nbt import from_snbt
from structura_core.entity_positions import shift_entity
from structura_core.world_entities import EntityLocation


@dataclass(frozen=True)
class EntityData:
    record: str
    location: Optional[EntityLocation] = None

    def unpack(self):
        return from_snbt(self.record)

    def shifted(self, offset):
        return EntityData(shift_entity(self.unpack(), offset).to_snbt(), self.location)


def entity_key(record):
    payload = record["nbt"]
    identity = payload.get("UUID")
    if identity is None and "UUIDMost" in payload and "UUIDLeast" in payload:
        identity = f'{payload["UUIDMost"]}:{payload["UUIDLeast"]}'
    return "uuid:" + str(identity) if identity is not None else "nbt:" + sha256(record.to_snbt().encode()).hexdigest()


def initial_entities(structure, locations=None):
    locations = locations or (None,) * len(structure.entities)
    return {(entity_key(record) if location is not None else f"entity:{index}"): EntityData(record.to_snbt(), location)
            for index, (record, location) in enumerate(zip(structure.entities, locations))}


def entity_change(session, label, deltas):
    from .changes import ChangeSet
    from .document_resize import placement_extent

    positions = [tuple(floor(float(v)) for v in delta.after.unpack()["pos"]) for delta in deltas if delta.after is not None]
    resize = None
    if positions and not hasattr(session, "world_changes"):
        lower = tuple(min(p[axis] for p in positions) for axis in range(3))
        size = tuple(max(p[axis] for p in positions) + 1 - lo for axis, lo in enumerate(lower))
        resize = placement_extent(session, lower, size)
    change = ChangeSet(session._id, session.revision, label, (), tuple(deltas), resize)
    session._check_change(change)
    return change


def check_entities(session, changes, bounds):
    from .changes import StaleChangeError
    from structura_core.structure import Structure
    from amulet_nbt import CompoundTag, IntTag, ListTag

    seen = set()
    for delta in changes:
        if delta.key in seen:
            raise ValueError("Duplicate entity change")
        seen.add(delta.key)
        if session._entities.get(delta.key) != delta.before:
            raise StaleChangeError("The selected entity changed; reopen its inspector")
        if delta.after is not None:
            record = delta.after.unpack()
            Structure.from_root(CompoundTag({"DataVersion": IntTag(session._document.source.data_version), "size": ListTag([IntTag(v) for v in session.size]),
                                            "palette": ListTag(), "blocks": ListTag(), "entities": ListTag([record])}))
            if not all(lo <= float(v) < hi for lo, v, hi in zip(bounds[0], record["pos"], bounds[1])):
                raise ValueError("Entity destination is outside the loaded area")


def write_entities(entities, changes, *, reverse=False):
    for delta in changes:
        value = delta.before if reverse else delta.after
        if value is None:
            entities.pop(delta.key, None)
        else:
            entities[delta.key] = value
