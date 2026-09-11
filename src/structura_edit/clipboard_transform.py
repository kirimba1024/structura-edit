from dataclasses import replace
from functools import lru_cache

from structura_core.block_transform import transform_state
from structura_core.grid_transform import GridTransform

from .cell_set import CellSet
from .clipboard_entities import transform_entities


@lru_cache(maxsize=1)
def _versions():
    import PyMCTranslate

    return PyMCTranslate.new_translation_manager()


def transform_clipboard(clipboard, *, turns=0, axis="y", flip=None):
    operation = GridTransform.operation(turns=turns, axis=axis, flip=flip)
    transform = operation.compose(clipboard.orientation)
    original = clipboard.transform_source or clipboard
    if transform == GridTransform():
        return original
    version = _versions().get_version("java", original.data_version)
    states = {}
    for state in {cell.state for _, cell in original.cells}:
        name = state.split("[", 1)[0]
        try:
            specification = version.block.get_specification(*name.split(":", 1), force_blockstate=True)
            defaults, allowed = specification.default_properties, specification.valid_properties
        except KeyError:
            defaults, allowed = {}, {}
        states[state] = transform_state(state, transform, defaults=defaults, allowed=allowed)
    cells = []
    for position, cell in original.cells:
        state = states[cell.state]
        cells.append((transform.point(position, original.size, cell=True),
                      cell if state == cell.state else replace(cell, state=state, variant=None)))
    footprint = None
    if original.footprint is not None:
        footprint = CellSet.from_positions(transform.point(position, original.size, cell=True)
                                           for position in original.footprint.positions())
    return replace(original, size=transform.size(original.size), cells=tuple(cells),
                   entities=transform_entities(original.entities, original.size, transform), footprint=footprint,
                   anchor=transform.point(original.anchor, original.size, cell=True) if original.anchor is not None else None,
                   transform_source=original, orientation=transform)
