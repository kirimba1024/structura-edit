from copy import deepcopy

from amulet_nbt import CompoundTag, IntArrayTag, IntTag, ListTag


def wrapped_block_entity(original, generated):
    wrapper = deepcopy(original)
    payload = deepcopy(generated)
    wrapper.update({"Pos": payload.pop("Pos"), "Id": payload.pop("Id"), "Data": payload})
    return wrapper


def updated_block_entities(schematic, generated, cells):
    blocks = schematic.root if schematic.version == 2 else schematic.root["Blocks"]
    records = blocks.get("BlockEntities", ())
    originals = {tuple(int(v) for v in record["Pos"]): record for record in records}
    replacements = {tuple(int(v) for v in record["Pos"]): record for record in generated}
    retained = [record for record in records if tuple(int(v) for v in record["Pos"]) not in cells]
    for position, cell in cells.items():
        if not cell.keep_nbt:
            continue
        if cell.data is None and cell.origin in originals:
            record = deepcopy(originals[cell.origin])
            record["Pos"] = IntArrayTag(position)
            payload = record.get("Data", record) if schematic.version == 3 else record
            for axis, old, new in zip("xyz", cell.origin, position):
                if axis in payload and old != new:
                    payload[axis] = IntTag(int(payload[axis]) + new - old)
        elif position in replacements:
            record = replacements[position]
            if schematic.version == 3:
                record = wrapped_block_entity(originals.get(cell.origin, CompoundTag()), record)
            else:
                record = deepcopy(record)
        else:
            continue
        retained.append(record)
    return ListTag(retained)


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
