import math
import re

from amulet_nbt import (
    ByteArrayTag, ByteTag, CompoundTag, DoubleTag, FloatTag, IntArrayTag,
    IntTag, ListTag, LongArrayTag, LongTag, ShortTag, StringTag,
)


ARRAY_VALUES = {ByteArrayTag: ByteTag, IntArrayTag: IntTag, LongArrayTag: LongTag}
CONTAINERS = (CompoundTag, ListTag, *ARRAY_VALUES)
INTEGER_BITS = {ByteTag: 8, ShortTag: 16, IntTag: 32, LongTag: 64}
SCALARS = (*INTEGER_BITS, FloatTag, DoubleTag, StringTag)


def at_path(root, path):
    value = root
    for key in path:
        parent, value = value, value[key]
        if type(parent) in ARRAY_VALUES:
            value = ARRAY_VALUES[type(parent)](int(value))
    return value


def replace_value(root, path, value):
    if not path:
        if not isinstance(value, CompoundTag):
            raise ValueError("The object root must remain an NBT compound")
        return value
    parents = [root]
    for key in path[:-1]:
        parents.append(parents[-1][key])
    for parent, key in reversed(list(zip(parents, path))):
        if isinstance(parent, ListTag) and value.tag_id != parent.list_data_type:
            raise ValueError("List entries must keep the same NBT type")
        if type(parent) in ARRAY_VALUES and type(value) is not ARRAY_VALUES[type(parent)]:
            raise ValueError("Array entries must keep the same NBT type")
        copy = type(parent)(parent.np_array.copy() if type(parent) in ARRAY_VALUES else parent)
        copy[key] = value
        value = copy
    return value


def scalar_text(value):
    return str(value) if isinstance(value, StringTag) else repr(value.py_data)


def parse_scalar(original, text):
    tag = type(original)
    if tag is StringTag:
        return StringTag(text)
    if tag in INTEGER_BITS:
        if not re.fullmatch(r"[+-]?[0-9]+", text.strip()):
            raise ValueError("Enter a whole number")
        value = int(text)
        bound = 1 << (INTEGER_BITS[tag] - 1)
        if not -bound <= value < bound:
            raise ValueError(f"Enter a number from {-bound} to {bound - 1}")
        return tag(value)
    if tag in (FloatTag, DoubleTag):
        try:
            value = float(text)
        except ValueError:
            raise ValueError("Enter a number, for example 1.5 or 2e3") from None
        if not math.isfinite(value):
            raise ValueError("Enter a finite number")
        result = tag(value)
        if not math.isfinite(float(result)):
            raise ValueError("This number is too large for the stored type")
        return result
    raise ValueError("Use NBT text to edit this value")


def path_text(path):
    return " / ".join(map(str, path)) or "Object"


def value_summary(value):
    return f"{len(value):,} entries" if isinstance(value, CONTAINERS) else str(value)[:200]
