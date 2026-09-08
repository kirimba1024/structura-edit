from dataclasses import replace
from math import isfinite

from amulet_nbt import CompoundTag, IntTag, StringTag, from_snbt

from .cell_data import CellData, cell_payload, detached_cell
from .changes import ChangeSet, EntityDelta, _Delta, _position
from .entity_data import EntityData, entity_change, entity_key
from .entity_transform import new_identity, position_record, transform_record


def compound(value):
    value = from_snbt(value) if isinstance(value, str) else value
    if not isinstance(value, CompoundTag):
        raise ValueError("Object data must be an NBT compound: {key: value}")
    return CompoundTag(value)


def block_data(session, position):
    position = _position(position)
    state = session.state_at(position)
    if state is None:
        raise ValueError("There is no block at this position")
    cell = session._cell(position)
    return state, cell_payload(session._document.source, cell, position) or CompoundTag()


def edit_block_data(session, position, text):
    position = _position(position)
    block_data(session, position)
    before = session._cell(position)
    payload = compound(text)
    for axis in "xyz":
        if axis in payload:
            payload[axis] = IntTag(0)
    detached = detached_cell(session._document.source, before, position)
    data = CellData(payload.to_snbt() if payload else None, detached.data.record if detached.data else None)
    after = replace(detached, keep_nbt=bool(payload), data=data)
    if detached == after:
        return ChangeSet(session._id, session.revision, "Edit block data", ())
    return ChangeSet(session._id, session.revision, "Edit block data", (_Delta(position, before, after),))


def entity_items(session, selection=None):
    for key, data in session._entities.items():
        record = data.unpack()
        position = tuple(float(v) for v in record["pos"])
        if selection is None or position in selection:
            yield key, record


def select_entities(session, selection=None):
    if selection is None:
        return tuple(session._entities)
    return tuple(key for key, _ in entity_items(session, selection))


def edit_entity_data(session, key, text):
    before = session._entities[key]
    record = before.unpack()
    payload = compound(text)
    if not isinstance(payload.get("id"), StringTag) or not str(payload["id"]):
        raise ValueError("An entity needs a non-empty string id")
    if before.location is not None:
        for name in ("UUID", "UUIDMost", "UUIDLeast", "Dimension"):
            if payload.get(name) != record["nbt"].get(name):
                raise ValueError(f"Keep {name} unchanged; it identifies this entity in the world")
        if before.location.storage == "player" and payload["id"] != record["nbt"]["id"]:
            raise ValueError("A player cannot be changed into another entity type")
    record["nbt"] = payload
    if "Pos" in payload:
        position = tuple(float(v) for v in payload["Pos"])
        position_record(record, position)
    after = EntityData(record.to_snbt(), before.location)
    deltas = () if after == before else (EntityDelta(key, before, after),)
    return entity_change(session, "Edit entity data", deltas)


def transform_entities(session, keys, *, action="Move", offset=(0, 0, 0), angle=0):
    keys = tuple(dict.fromkeys(keys))
    if not keys:
        raise ValueError("Select at least one entity")
    if action not in ("Move", "Duplicate", "Rotate", "Delete"):
        raise ValueError("Unknown entity action")
    offset = tuple(float(v) for v in offset)
    if len(offset) != 3 or not all(isfinite(v) for v in (*offset, angle)):
        raise ValueError("Use finite offsets and rotation")
    records = [(key, session._entities[key], session._entities[key].unpack()) for key in keys]
    center = tuple(sum(float(record["pos"][axis]) for _, _, record in records) / len(records) for axis in range(3))
    deltas = []
    for key, before, record in records:
        location = before.location
        if before.location is not None and before.location.storage == "player" and action in ("Delete", "Duplicate"):
            raise ValueError("Player profiles can be inspected, moved and edited; exclude players to duplicate or delete a group")
        if action == "Delete":
            deltas.append(EntityDelta(key, before, None))
            continue
        if action == "Rotate":
            transform_record(record, angle=angle, center=center)
        else:
            transform_record(record, offset=offset)
        if action == "Duplicate":
            new_identity(record["nbt"])
            key, before = entity_key(record), None
        after = EntityData(record.to_snbt(), location)
        if after != before:
            deltas.append(EntityDelta(key, before, after))
    return entity_change(session, f"{action} entities", deltas)


def prepare_object_change(session, operation, **args):
    if operation == "select":
        return select_entities(session, **args)
    if operation == "inspect":
        return inspect_objects(session, **args)
    if operation == "edit":
        return edit_objects(session, **args)
    if operation == "entity_data":
        return edit_entity_data(session, **args)
    if operation == "block_data":
        return edit_block_data(session, **args)
    return transform_entities(session, **args)


def inspect_objects(session, keys=(), position=None):
    from structura_core import parse_state

    records = []
    for key in keys:
        record = session._entities[key].unpack()
        position_text = ", ".join(f"{float(v) + o:.2f}" for v, o in zip(record["pos"], session.origin))
        records.append(dict(kind="entity", key=key, title=f'{record["nbt"].get("id", "entity")} · {position_text}',
                            text=record["nbt"].to_snbt(), root=record["nbt"]))
    if position is not None and not keys:
        state, payload = block_data(session, position)
        wrapper = CompoundTag({"state": parse_state(state), "data": payload})
        records.append(dict(kind="block", position=position, title=f"{state} · {tuple(p + o for p, o in zip(position, session.origin))}",
                            text=wrapper.to_snbt(), root=wrapper))
    return records


def edit_objects(session, edits):
    from structura_core import state_key

    branch = session.fork()
    entities = []
    for record, text in edits:
        if record["kind"] == "entity":
            entities.extend(edit_entity_data(session, record["key"], text).entities)
        else:
            wrapper = compound(text)
            branch.apply(branch.set_block(record["position"], state_key(wrapper["state"])))
            branch.apply(edit_block_data(branch, record["position"], wrapper["data"].to_snbt()))
    blocks = session.diff(branch, "Edit object data")
    change = entity_change(session, blocks.label, entities)
    result = replace(blocks, entities=change.entities, resize=change.resize)
    session._check_change(result)
    return result
