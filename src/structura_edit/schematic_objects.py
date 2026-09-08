from copy import deepcopy

from amulet_nbt import CompoundTag, ListTag


def updated_entities(schematic, entities):
    originals = schematic.root.get("Entities", ())
    result = ListTag()
    for key, value in entities.items():
        wrapper = value.unpack()
        index = int(key.split(":", 1)[1]) if key.startswith("entity:") else -1
        record = deepcopy(originals[index]) if 0 <= index < len(originals) else CompoundTag()
        payload = deepcopy(wrapper["nbt"])
        identity = payload.pop("id", None)
        if identity is None:
            raise ValueError("Entity data needs an id for Sponge save")
        if schematic.version == 3:
            record["Data"] = payload
        else:
            record = payload
        record["Id"] = identity
        record["Pos"] = deepcopy(wrapper["pos"])
        result.append(record)
    return result
