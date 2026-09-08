from copy import deepcopy
from math import cos, floor, isfinite, radians, sin
from uuid import uuid4

from amulet_nbt import DoubleTag, FloatTag, IntArrayTag, IntTag, ListTag, StringTag
from structura_core.entity_positions import HANGING_ENTITIES


HORIZONTAL = ("south", "west", "north", "east")
DIRECTIONS = ("down", "up", "north", "south", "west", "east")
ANCHORS = ("TileX", "TileY", "TileZ")


def position_record(record, position):
    if len(position) != 3 or not all(isfinite(v) for v in position):
        raise ValueError("Entity position must contain three finite numbers")
    record["pos"] = ListTag([DoubleTag(v) for v in position])
    payload = record["nbt"]
    block = tuple(floor(v) for v in position)
    if str(payload.get("id", "")) in HANGING_ENTITIES and all(axis in payload for axis in ANCHORS):
        block = tuple(int(payload[axis]) for axis in ANCHORS)
    record["blockPos"] = ListTag([IntTag(v) for v in block])
    if "Pos" in payload:
        payload["Pos"] = deepcopy(record["pos"])
    return record


def payloads(root):
    pending = [root]
    while pending:
        payload = pending.pop()
        yield payload
        pending.extend(payload.get("Passengers", ()))


def new_identity(root):
    for payload in payloads(root):
        value = uuid4().int
        payload["UUID"] = IntArrayTag([((value >> shift) & 0xffffffff) - (0x100000000 if (value >> shift) & 0x80000000 else 0)
                                       for shift in (96, 64, 32, 0)])
        payload.pop("UUIDMost", None)
        payload.pop("UUIDLeast", None)


def _turn_facing(payload, angle, flip):
    turns = round(angle / 90)
    if abs(angle / 90 - turns) > 1e-8:
        raise ValueError("Hanging entities rotate in multiples of 90 degrees")
    for key in ("facing", "Facing", "Direction"):
        if key not in payload:
            continue
        value = payload[key]
        names = DIRECTIONS if key == "Facing" else HORIZONTAL
        direction = str(value) if isinstance(value, StringTag) else names[int(value) % len(names)]
        mirrors = {"east": "west", "west": "east"} if flip == "x" else {"north": "south", "south": "north"} if flip == "z" else {}
        direction = mirrors.get(direction, direction)
        if direction in HORIZONTAL:
            direction = HORIZONTAL[(HORIZONTAL.index(direction) + turns) % 4]
            payload[key] = StringTag(direction) if isinstance(value, StringTag) else type(value)(names.index(direction))


def transform_record(record, *, offset=(0, 0, 0), angle=0, center=(0, 0, 0), flip=None):
    if flip not in (None, "x", "z"):
        raise ValueError("Mirror entities on X or Z")
    cosine, sine = cos(radians(angle)), sin(radians(angle))
    def horizontal(x, z):
        x, z = (-x if flip == "x" else x), (-z if flip == "z" else z)
        return x * cosine - z * sine, x * sine + z * cosine
    def transform(position):
        x, y, z = map(float, position)
        if angle or flip:
            x, z = horizontal(x - center[0], z - center[2])
            x, z = x + center[0], z + center[2]
        return tuple(round(v + d, 10) for v, d in zip((x, y, z), offset))
    position = transform(record["pos"])
    anchor = transform(tuple(int(v) + 0.5 for v in record["blockPos"]))
    for payload in payloads(record["nbt"]):
        if "Pos" in payload:
            payload["Pos"] = ListTag([DoubleTag(v) for v in transform(payload["Pos"])])
        if angle or flip:
            orientation = payload.get("Rotation", ListTag([FloatTag(0), FloatTag(0)]))
            yaw = float(orientation[0])
            yaw = -yaw if flip == "x" else 180 - yaw if flip == "z" else yaw
            payload["Rotation"] = ListTag([FloatTag((yaw + angle) % 360), FloatTag(float(orientation[1]))])
            if "Motion" in payload:
                vx, vy, vz = map(float, payload["Motion"])
                vx, vz = horizontal(vx, vz)
                payload["Motion"] = ListTag([DoubleTag(round(v, 10)) for v in (vx, vy, vz)])
        if str(payload.get("id", "")) in HANGING_ENTITIES:
            if all(axis in payload for axis in ANCHORS):
                tile = transform(tuple(int(payload[axis]) + 0.5 for axis in ANCHORS))
                payload.update({axis: IntTag(floor(v)) for axis, v in zip(ANCHORS, tile)})
            if angle or flip:
                _turn_facing(payload, angle, flip)
    position_record(record, position)
    if str(record["nbt"].get("id", "")) in HANGING_ENTITIES:
        record["blockPos"] = ListTag([IntTag(floor(v)) for v in anchor])
    return record
