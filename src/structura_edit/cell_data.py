from copy import deepcopy
from dataclasses import dataclass, replace
from typing import Optional

from amulet_nbt import IntTag, from_snbt


@dataclass(frozen=True)
class CellData:
    nbt: Optional[str] = None
    record: Optional[str] = None


def cell_payload(base, cell, position):
    if not cell.keep_nbt:
        return None
    if cell.data is not None:
        payload = from_snbt(cell.data.nbt) if cell.data.nbt else None
        origin = (0, 0, 0)
    else:
        payload = deepcopy(base.block_nbt.get(cell.origin))
        origin = cell.origin
    if payload is not None:
        for axis, old, new in zip("xyz", origin, position):
            if axis in payload and old != new:
                payload[axis] = IntTag(int(payload[axis]) + new - old)
    return payload


def cell_record(base, cell):
    if cell.data is not None:
        return from_snbt(cell.data.record) if cell.data.record else None
    return deepcopy(base._block_records.get(cell.origin))


def detached_cell(base, cell, position):
    payload = cell_payload(base, cell, position)
    if payload is not None:
        for axis in "xyz":
            if axis in payload:
                payload[axis] = IntTag(0)
    record = cell_record(base, cell)
    if record is not None:
        for key in ("pos", "state", "nbt"):
            record.pop(key, None)
    data = CellData(payload.to_snbt() if payload is not None else None, record.to_snbt() if record else None)
    return replace(cell, data=data if data.nbt or data.record else None)


def material_data(cell, keep_nbt):
    if cell is None or cell.data is None:
        return None
    data = CellData(cell.data.nbt if keep_nbt else None, cell.data.record)
    return data if data.nbt or data.record else None
