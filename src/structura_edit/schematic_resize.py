from copy import deepcopy
from math import prod

import numpy as np
from amulet_nbt import ByteArrayTag, CompoundTag, IntArrayTag, ListTag
from structura_core.export_schematic import _encode_varints, schematic_root
from structura_core.schematic import _palette, _varints

from .schematic_objects import updated_entities, wrapped_block_entity


def save_resized(schematic, structure, entities, path, cells):
    output = deepcopy(schematic)
    encoded = schematic_root(structure)
    for key in ("Width", "Height", "Length"):
        output.root[key] = encoded[key]
    origin = tuple(getattr(structure, "source_origin", schematic.offset))
    shift = tuple(old - new for old, new in zip(schematic.offset, origin))
    output.root["Offset"] = IntArrayTag(origin)
    if output.version == 2:
        for key in ("Palette", "PaletteMax", "BlockData", "BlockEntities"):
            output.root[key] = encoded[key]
    else:
        blocks = output.root.setdefault("Blocks", CompoundTag())
        blocks["Palette"] = encoded["Palette"]
        blocks["Data"] = encoded["BlockData"]
        originals = {tuple(int(v) + d for v, d in zip(record["Pos"], shift)): record
                     for record in blocks.get("BlockEntities", ())}
        records = ListTag()
        for record in encoded["BlockEntities"]:
            position = tuple(int(v) for v in record["Pos"])
            cell = cells.get(position)
            origin = cell.origin if cell is not None else position
            records.append(wrapped_block_entity(originals.get(origin, CompoundTag()), record))
        blocks["BlockEntities"] = records
    output.root["Entities"] = updated_entities(schematic, entities)
    if output.version == 2 and "BiomeData" in output.root:
        palette = _palette(output.root["BiomePalette"], "BiomePalette")
        old_shape, new_shape = (schematic.size[2], schematic.size[0]), (structure.size[2], structure.size[0])
        output.root["BiomeData"] = _biomes(output.root["BiomeData"], palette, old_shape, new_shape, (shift[2], shift[0]))
    elif output.version == 3 and "Biomes" in output.root:
        biomes = output.root["Biomes"]
        palette = _palette(biomes["Palette"], "Biome Palette")
        order = (1, 2, 0)
        biomes["Data"] = _biomes(biomes["Data"], palette, tuple(schematic.size[i] for i in order),
                                  tuple(structure.size[i] for i in order), tuple(shift[i] for i in order))
    return output.save(path)


def _biomes(data, palette, old_shape, new_shape, shift):
    before = np.fromiter(_varints(data, prod(old_shape), palette, "BiomeData"), dtype=np.int32).reshape(old_shape)
    after = np.full(new_shape, int(before.flat[0]), dtype=np.int32)
    after[tuple(slice(delta, delta + size) for delta, size in zip(shift, old_shape))] = before
    return ByteArrayTag(np.frombuffer(_encode_varints(after.ravel()), dtype=np.int8))
