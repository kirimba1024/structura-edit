from copy import copy, deepcopy
from pathlib import Path

from amulet_nbt import CompoundTag
from structura_core import load_structure
from structura_core.export_schematic import schematic_root
from structura_core.nbt import parse_state, save_structure
from structura_core.schematic import Schematic
from structura_core.world_backup import digest
from structura_core.compatibility import source_capabilities

from .cell_data import cell_payload, cell_record
from .schematic_objects import updated_block_entities, updated_entities


def copy_structure(structure):
    return deepcopy(structure, {id(structure.present): structure.present.copy()})


def compact_structure(structure):
    source = copy(structure)
    source._root = CompoundTag({key: value for key, value in structure._root.items() if key not in ("blocks", "entities")})
    source._block_records = {}
    for position, record in structure._block_records.items():
        extra = CompoundTag({key: value for key, value in record.items() if key not in ("pos", "state", "nbt")})
        if extra:
            source._block_records[position] = extra
    return copy_structure(source)


class Document:
    @property
    def capabilities(self):
        return source_capabilities(self.source_format, self.source.data_version, schema=getattr(self.native, "version", None))

    def __init__(self, structure, *, path=None, native=None, readonly=False):
        structure.validate()
        self.source = compact_structure(structure)
        self.path = Path(path) if path is not None else None
        self.native = native
        self.readonly = readonly
        self.origin = tuple(getattr(structure, "source_origin", (0, 0, 0)))
        self.source_hash = digest(self.path) if self.path is not None and self.path.is_file() else None
        self.source_format = "world" if self.path is not None and self.path.is_dir() else self.path.suffix.lower() if self.path else ".nbt"

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
        return cls(structure, path=path, readonly=suffix not in (".nbt", ".snbt", ".schematic"))

    def snapshot(self, cells, entities):
        structure = copy_structure(self.source)
        literal_indices = {}
        for position, cell in cells.items():
            index = cell.variant
            if index is None:
                if cell.state not in literal_indices:
                    literal_indices[cell.state] = len(structure.palette_raw)
                    for palette in structure.palettes_raw:
                        palette.append(parse_state(cell.state))
                index = literal_indices[cell.state]
            structure.present[position] = index
            structure.block_nbt.pop(position, None)
            if cell.keep_nbt:
                structure.block_nbt[position] = cell_payload(self.source, cell, position)
            if cell.origin != position or cell.data is not None:
                record = cell_record(self.source, cell)
                if record is None:
                    structure._block_records.pop(position, None)
                else:
                    structure._block_records[position] = record
        structure.entities = [value.unpack() for value in entities.values()]
        structure.validate()
        return structure

    def save(self, structure, path, cells, entities=None):
        if self.readonly:
            raise ValueError("This source is view-only in this release")
        path = Path(path)
        if isinstance(self.native, Schematic):
            if path.suffix.lower() != ".schem":
                raise ValueError("Save this document as .schem; format conversion is a separate operation")
            if structure.size != self.native.size or self.origin != self.native.offset:
                from .schematic_resize import save_resized

                return save_resized(self.native, structure, entities or {}, path, cells)
            output = deepcopy(self.native)
            if cells:
                encoded = schematic_root(structure)
                blocks = output.root if output.version == 2 else output.root.setdefault("Blocks", type(output.root)())
                blocks["Palette"] = encoded["Palette"]
                blocks["BlockData" if output.version == 2 else "Data"] = encoded["BlockData"]
                if output.version == 2:
                    blocks["PaletteMax"] = encoded["PaletteMax"]
                blocks["BlockEntities"] = updated_block_entities(output, encoded["BlockEntities"], cells)
            if entities is not None and [value.unpack() for value in entities.values()] != self.source.entities:
                output.root["Entities"] = updated_entities(output, entities)
            output.save(path)
        else:
            if path.suffix.lower() not in (".nbt", ".snbt"):
                raise ValueError("Save this document as .nbt or .snbt")
            save_structure(structure, path, structure.size)
        return path
