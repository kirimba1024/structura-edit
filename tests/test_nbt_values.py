import math

import pytest
from amulet_nbt import (
    ByteTag, DoubleTag, FloatTag, IntTag, LongTag, ShortTag, StringTag, from_snbt,
)

from structura_edit.nbt_values import at_path, parse_scalar, replace_value, scalar_text


@pytest.mark.parametrize("tag,bits", [(ByteTag, 8), (ShortTag, 16), (IntTag, 32), (LongTag, 64)])
def test_integer_edit_preserves_exact_type_range_and_precision(tag, bits):
    bound = 1 << (bits - 1)
    for number in (-bound, 0, bound - 1):
        value = parse_scalar(tag(0), str(number))
        assert type(value) is tag and int(value) == number
    for number in (-bound - 1, bound):
        with pytest.raises(ValueError, match="from"):
            parse_scalar(tag(0), str(number))
    with pytest.raises(ValueError, match="whole"):
        parse_scalar(tag(0), "1.5")


@pytest.mark.parametrize("tag", [FloatTag, DoubleTag])
def test_decimal_edit_keeps_precision_and_rejects_nonfinite(tag):
    original = tag(0.12345678901234567)
    assert parse_scalar(original, scalar_text(original)) == original
    assert float(parse_scalar(original, "-2.75e3")) == -2750
    for text in ("NaN", "Inf", "1e1000", "-Infinity"):
        with pytest.raises(ValueError, match="finite"):
            parse_scalar(original, text)
    with pytest.raises(ValueError, match="large"):
        parse_scalar(FloatTag(0), "1e100")
    assert math.isfinite(float(parse_scalar(DoubleTag(0), "1e100")))


def test_text_edit_is_literal_and_keeps_spaces_quotes_and_newlines():
    text = '  {"mod:label": "hello"}\nnext line  '
    assert str(parse_scalar(StringTag(""), text)) == text
    assert str(parse_scalar(StringTag("old"), "")) == ""


def test_nested_changes_do_not_mutate_search_snapshot_or_unknown_tags():
    original = from_snbt('{storage:{slots:[{id:"mod:gem",Count:2b,extra:{keep:9223372036854775807L}}]},other:[I;1,2]}')
    before = original.to_snbt()
    path = ("storage", "slots", 0, "Count")
    changed = replace_value(original, path, ByteTag(7))
    assert original.to_snbt() == before
    assert at_path(changed, path) == ByteTag(7)
    assert changed["storage"]["slots"][0]["extra"] == original["storage"]["slots"][0]["extra"]
    restored = replace_value(changed, path, ByteTag(2))
    assert restored == original


@pytest.mark.parametrize("snbt,tag", [("[B;1b,2b]", ByteTag), ("[I;1,2]", IntTag), ("[L;1L,2L]", LongTag)])
def test_array_edit_is_detached_and_keeps_element_type(snbt, tag):
    original = from_snbt("{values:" + snbt + "}")
    changed = replace_value(original, ("values", 1), tag(42))
    assert int(original["values"][1]) == 2
    assert at_path(changed, ("values", 1)) == tag(42)
    with pytest.raises(ValueError, match="same NBT type"):
        replace_value(original, ("values", 1), StringTag("42"))


def test_invalid_container_edit_is_atomic():
    original = from_snbt('{values:[1b,2b],other:{keep:7L}}')
    before = original.to_snbt()
    with pytest.raises(ValueError, match="same NBT type"):
        replace_value(original, ("values", 1), IntTag(2))
    with pytest.raises(ValueError, match="root"):
        replace_value(original, (), IntTag(2))
    assert original.to_snbt() == before
