from dataclasses import replace
from functools import lru_cache
from numbers import Integral

from amulet_nbt import CompoundTag, StringTag
from structura_core import parse_state, state_key


COMPASS = ("north", "east", "south", "west")
SPATIAL = {"facing", "axis", "rotation", "shape", "hinge", "type", "orientation", *COMPASS}
MIRRORS = {"x": {"east": "west", "west": "east"}, "z": {"north": "south", "south": "north"}}


@lru_cache(maxsize=1)
def _versions():
    import PyMCTranslate

    return PyMCTranslate.new_translation_manager()


def _state(state, version, directions, turns, flip):
    raw = parse_state(state)
    name = str(raw["Name"])
    original = {key: str(value) for key, value in raw.get("Properties", {}).items()}
    try:
        defaults = version.block.get_specification(*name.split(":", 1), force_blockstate=True).default_properties
    except KeyError:
        defaults = {}
    props = {key: str(value) for key, value in defaults.items() if key in SPATIAL}
    props.update(original)
    mapped = {}
    for key, value in props.items():
        if key == "facing":
            value = directions.get(value, value)
        elif key == "axis" and turns % 2:
            value = {"x": "z", "z": "x"}.get(value, value)
        elif key == "rotation":
            angle = int(value)
            if not 0 <= angle < 16:
                raise ValueError(f"Unsupported block rotation: {name}")
            angle = -angle if flip == "x" else 8 - angle if flip == "z" else angle
            value = str((angle + turns * 4) % 16)
        elif key == "orientation":
            value = "_".join(directions.get(part, part) for part in value.split("_"))
        elif key == "shape":
            parts = value.split("_")
            if len(parts) == 2 and parts[1] in COMPASS:
                parts = [directions.get(part, part) for part in parts]
                if parts[0] != "ascending":
                    parts.sort(key=("north", "south", "east", "west").index)
                value = "_".join(parts)
            elif flip and value in ("inner_left", "inner_right", "outer_left", "outer_right"):
                stem, side = value.rsplit("_", 1)
                value = stem + "_" + ("right" if side == "left" else "left")
        elif flip and key in ("hinge", "type"):
            value = {"left": "right", "right": "left"}.get(value, value)
        target = directions.get(key, key)
        if key in original or value != str(defaults.get(target, "")):
            mapped[target] = StringTag(value)
    raw.pop("Properties", None)
    if mapped:
        raw["Properties"] = CompoundTag(mapped)
    return state_key(raw)


def transform_clipboard(clipboard, *, turns=0, flip=None):
    if isinstance(turns, bool) or not isinstance(turns, Integral) or flip not in (None, "x", "z"):
        raise ValueError("Use integer quarter turns and flip X or Z")
    turns %= 4
    if not turns and flip is None:
        return clipboard
    mirrored = MIRRORS.get(flip, {})
    directions = {name: COMPASS[(COMPASS.index(mirrored.get(name, name)) + turns) % 4] for name in COMPASS}
    version = _versions().get_version("java", clipboard.data_version)
    states = {cell.state for _, cell in clipboard.cells}
    states = {state: _state(state, version, directions, turns, flip) for state in states}
    sx, sy, sz = clipboard.size
    cells = []
    for (x, y, z), cell in clipboard.cells:
        width, depth = sx, sz
        x, z = (sx - 1 - x if flip == "x" else x), (sz - 1 - z if flip == "z" else z)
        for _ in range(turns):
            x, z, width, depth = depth - 1 - z, x, depth, width
        state = states[cell.state]
        cells.append(((x, y, z), cell if state == cell.state else replace(cell, state=state, variant=None)))
    return replace(clipboard, size=(sz, sy, sx) if turns % 2 else clipboard.size, cells=tuple(cells))
