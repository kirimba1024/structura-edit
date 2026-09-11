from pathlib import Path
import struct
import zlib

import numpy as np
from amulet_nbt import ByteTag, CompoundTag, IntTag, ListTag, LongArrayTag, NamedTag, StringTag, from_snbt

from structura_core.nbt import parse_state, write_root


def create_overview_world(directory, *, layout="surface"):
    from amulet.utils.world_utils import encode_long_array

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    write_root(from_snbt('{Data:{DataVersion:3955,LevelName:"Overview test",SpawnX:8,SpawnY:12,SpawnZ:8}}'), directory / "level.dat")
    regions = {}
    for cx, cz in ((-1, -1), (-1, 0), (0, -1), (0, 0), (1, 0), (2, 0)):
        blocks = np.zeros((16, 16, 16), np.uint16)
        blocks[:4] = 1
        blocks[4] = 2
        blocks[7, 6:9] = 3
        blocks[5:10, 12:14, 12:14] = 4
        if layout == "nether":
            blocks[:2] = 1
            blocks[10:12] = 1
            blocks[15, 4:8, 4:8] = 3
        elif layout == "end":
            blocks[:] = 0
            if cx != 1:
                blocks[5:8, 3:12, 3:12] = 1
        section = CompoundTag({"Y": ByteTag(0), "block_states": CompoundTag({
            "palette": ListTag([parse_state(name) for name in ("minecraft:air", "minecraft:stone", "minecraft:grass_block",
                                                                 "minecraft:oak_planks", "minecraft:glass")]),
            "data": LongArrayTag(encode_long_array(blocks.ravel(), bits_per_entry=4, dense=False)),
        })})
        root = CompoundTag({"DataVersion": IntTag(3955), "xPos": IntTag(cx), "zPos": IntTag(cz),
                            "Status": StringTag("minecraft:full"), "sections": ListTag([section])})
        payload = b"\x02" + zlib.compress(NamedTag(root).save_to(compressed=False))
        record = struct.pack(">I", len(payload)) + payload
        regions.setdefault((cx // 32, cz // 32), []).append((cx, cz, record))
    folder = "DIM-1" if layout == "nether" else "DIM1" if layout == "end" else "dimensions/test/high" if layout == "custom" else ""
    region = directory / folder / "region"
    region.mkdir(parents=True, exist_ok=True)
    for (rx, rz), chunks in regions.items():
        header, body = bytearray(8192), bytearray()
        for cx, cz, record in chunks:
            sector = 2 + len(body) // 4096
            count = (len(record) + 4095) // 4096
            offset = 4 * (cx % 32 + 32 * (cz % 32))
            header[offset:offset + 4] = struct.pack(">I", sector * 256 + count)
            body.extend(record + b"\0" * (count * 4096 - len(record)))
        (region / f"r.{rx}.{rz}.mca").write_bytes(header + body)
    return directory
