from pathlib import Path

from structura_core.conversion_losses import conversion_losses
from structura_core.export_schematic import export_schematic
from structura_core.nbt import Structure, save_structure
from structura_core.structure_writer import structure_root


def selected_structure(session, selection):
    session._check_readable(selection)
    if selection.volume > session.operation_limit:
        raise ValueError("Export exceeds the cell budget; select a smaller region")
    source = session.snapshot()
    source.present = {p: i for p, i in source.present.items() if p in selection}
    source.block_nbt = {p: data for p, data in source.block_nbt.items() if p in selection}
    source._block_records = {p: data for p, data in source._block_records.items() if p in selection}
    source.entities = [e for e in source.entities if tuple(float(v) for v in e["pos"]) in selection]
    size = tuple(hi - lo for lo, hi in zip(selection.lower, selection.upper))
    root = structure_root(source, size, shift=tuple(-v for v in selection.lower))
    return Structure.from_root(root, palette_index=source.palette_index)


def export_losses(session, selection, path):
    source = selected_structure(session, selection)
    target = Path(path).suffix.lower()
    if target not in (".nbt", ".snbt", ".schem"):
        raise ValueError("Selection export uses NBT, SNBT or Sponge .schem")
    return conversion_losses(None, source, ".nbt" if target == ".snbt" else target, None)


def export_selection(session, selection, path):
    path = Path(path)
    source = selected_structure(session, selection)
    if path.suffix.lower() == ".schem":
        return export_schematic(source, path, offset=(0, 0, 0))
    if path.suffix.lower() not in (".nbt", ".snbt"):
        raise ValueError("Selection export uses NBT, SNBT or Sponge .schem")
    save_structure(source, path, source.size)
    return path
