from copy import deepcopy
from pathlib import Path

from amulet_nbt import CompoundTag, IntArrayTag, IntTag, ListTag
from structura_core import load_structure
from structura_core.export_schematic import schematic_root
from structura_core.nbt import save_structure
from structura_core.schematic import Schematic


def copy_structure(structure):
    positions = {id(position): position for position in structure.present}
    return deepcopy(structure, positions)


class Document:
    def __init__(self, structure, *, path=None, native=None, readonly=False):
        structure.validate()
        self.source = copy_structure(structure)
        self.path = Path(path) if path is not None else None
        self.native = native
        self.readonly = readonly
        self.origin = tuple(getattr(structure, "source_origin", (0, 0, 0)))

    @classmethod
    def open(cls, path, *, region=None, palette_index=0, source_data_version=None, target_version=None, strict=False):
        path = Path(path)
        suffix = path.suffix.lower()
        if suffix == ".schem":
            if region is not None or palette_index != 0:
                raise ValueError("Sponge input has one palette and no named regions")
            native = Schematic(path)
            if target_version is not None:
                raise ValueError("target_version applies only to Bedrock input")
            return cls(native.to_structure(data_version=source_data_version), path=path, native=native, readonly=native.version == 1)
        structure = load_structure(path, region=region, palette_index=palette_index,
                                   source_data_version=source_data_version, target_version=target_version, strict=strict)
        return cls(structure, path=path, readonly=suffix not in (".nbt", ".snbt"))

    def save(self, structure, path, cells):
        if self.readonly:
            raise ValueError("This source is view-only in this release")
        path = Path(path)
        if isinstance(self.native, Schematic):
            if path.suffix.lower() != ".schem":
                raise ValueError("Save this document as .schem; format conversion is a separate operation")
            output = deepcopy(self.native)
            if cells:
                encoded = schematic_root(structure)
                blocks = output.root if output.version == 2 else output.root.setdefault("Blocks", type(output.root)())
                blocks["Palette"] = encoded["Palette"]
                blocks["BlockData" if output.version == 2 else "Data"] = encoded["BlockData"]
                if output.version == 2:
                    blocks["PaletteMax"] = encoded["PaletteMax"]
                records = blocks.get("BlockEntities", ListTag())
                original = {tuple(int(v) for v in record["Pos"]): record for record in records}
                generated = {tuple(int(v) for v in record["Pos"]): record for record in encoded["BlockEntities"]}
                retained = [
                    record for record in records
                    if tuple(int(v) for v in record["Pos"]) not in cells
                ]
                for position, cell in cells.items():
                    if cell.keep_nbt and cell.origin in original:
                        record = deepcopy(original[cell.origin])
                        record["Pos"] = IntArrayTag(position)
                        payload = record.get("Data", record) if output.version == 3 else record
                        for axis, old, new in zip("xyz", cell.origin, position):
                            if axis in payload and old != new:
                                payload[axis] = IntTag(int(payload[axis]) + new - old)
                        retained.append(record)
                    elif cell.keep_nbt and position in generated:
                        record = deepcopy(generated[position])
                        if output.version == 3:
                            record = CompoundTag({"Pos": record.pop("Pos"), "Id": record.pop("Id"), "Data": record})
                        retained.append(record)
                blocks["BlockEntities"] = ListTag(retained)
            output.save(path)
        else:
            if path.suffix.lower() not in (".nbt", ".snbt"):
                raise ValueError("Save this document as .nbt or .snbt")
            save_structure(structure, path, structure.size)
        return path
