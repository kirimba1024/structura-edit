from dataclasses import asdict

from structura_core.world_entities import EntityLocation

from .cell_data import CellData
from .changes import _Cell
from .entity_data import EntityData


def encode(value):
    return asdict(value) if value is not None else None


def cell(value):
    if value is None:
        return None
    value = dict(value)
    value["origin"] = tuple(value["origin"]) if value.get("origin") is not None else None
    value["data"] = CellData(**value["data"]) if value.get("data") is not None else None
    return _Cell(**value)


def entity(value):
    if value is None:
        return None
    location = value.get("location")
    if location is not None:
        location = dict(location)
        if location.get("chunk") is not None:
            location["chunk"] = tuple(location["chunk"])
        location = EntityLocation(**location)
    return EntityData(value["record"], location)


def pack_patch(patch):
    return [[key, [encode(value) for value in pair]] for key, pair in patch.items()]


def unpack_patch(patch, decoder=cell):
    return {tuple(key) if isinstance(key, list) else key: tuple(decoder(value) for value in pair) for key, pair in patch}
