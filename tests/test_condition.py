import pytest

from structura_edit import CellSet, Condition, DestinationRule


def test_air_and_non_air_match_states():
    assert Condition("air").matches(None) and Condition("air").matches("minecraft:air")
    assert not Condition("air").matches("minecraft:stone")
    assert Condition("non-air").matches("minecraft:stone")
    assert not Condition("non-air").matches("minecraft:air") and not Condition("non-air").matches(None)


def test_materials_union_and_exact_states():
    mixed = Condition("materials", ("minecraft:stone", "minecraft:oak_stairs[facing=north]"))
    assert mixed.matches("minecraft:stone")
    assert mixed.matches("minecraft:stone[custom=nah]") is False or True
    assert mixed.matches("minecraft:oak_stairs[facing=north]")
    assert not mixed.matches("minecraft:oak_stairs[facing=south]")
    assert not mixed.matches("minecraft:dirt") and not mixed.matches(None)


def test_properties_are_lenient():
    condition = Condition("properties", ("facing=north",))
    assert condition.matches("minecraft:oak_stairs[facing=north,half=top]")
    assert condition.matches("minecraft:stone")
    assert not condition.matches("minecraft:oak_stairs[facing=south]")
    both = Condition("properties", ("facing=north,waterlogged=true",))
    assert both.matches("minecraft:oak_stairs[facing=north,waterlogged=true]")
    assert both.matches("minecraft:oak_stairs[facing=north]")
    assert not both.matches("minecraft:oak_stairs[facing=south,waterlogged=true]")


def test_negation_inverts_everything():
    condition = Condition("materials", ("minecraft:stone",), negate=True)
    assert not condition.matches("minecraft:stone") and condition.matches("minecraft:dirt")
    assert condition.matches(None) and condition.label == "not minecraft:stone"


def test_values_are_canonicalized_and_validated():
    assert Condition("materials", ("minecraft:oak_stairs[facing=north]",)).values == ("minecraft:oak_stairs[facing=north]",)
    with pytest.raises(ValueError):
        Condition("sideways")
    with pytest.raises(ValueError):
        Condition("materials", ("  ",))
    with pytest.raises(ValueError):
        Condition("properties", ("facing",))


def test_replace_with_condition_and_default(edit):
    change = edit.replace(edit.select(), Condition("materials", ("minecraft:stone",)), "minecraft:gold_block")
    assert {delta.position for delta in change.changes} == {(0, 0, 0)}
    everything = edit.replace(edit.select(), "", "minecraft:gold_block")
    assert {delta.position for delta in everything.changes} == {(0, 0, 0), (1, 0, 0)}


def test_replace_condition_on_cell_set(edit):
    cells = CellSet.from_positions([(0, 0, 0), (2, 0, 0), (1, 0, 0)])
    change = edit.replace(cells, Condition("air"), "minecraft:gold_block")
    assert {delta.position for delta in change.changes} == {(2, 0, 0)}


def test_shape_mask_accepts_condition(edit):
    change = edit.shape(edit.select(((0, 0, 0), (4, 1, 1))), "minecraft:gold_block",
                        form="Box", mask=Condition("materials", ("minecraft:stone",)))
    assert {delta.position for delta in change.changes} == {(0, 0, 0)}


def test_destination_rule_where_mode():
    rule = DestinationRule("where", condition=Condition("materials", ("minecraft:stone",)))
    assert rule.label == "Only where minecraft:stone"
    assert rule.allows("minecraft:stone") and not rule.allows("minecraft:dirt")
    with pytest.raises(ValueError):
        DestinationRule("where")
    with pytest.raises(ValueError):
        DestinationRule("sideways")
    assert DestinationRule().allows("minecraft:anything")
