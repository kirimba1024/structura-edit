import pytest

from structura_edit import DestinationRule
from structura_edit.clipboard_placement import plan_placement


def test_keep_existing_preserves_containers_and_only_fills_air(edit):
    clipboard = edit.copy(edit.select(((0, 0, 0), (2, 1, 1))))
    original = edit.snapshot().block_nbt[(1, 0, 0)]
    plan = plan_placement(edit, clipboard, ((1, 0, 0),), destination=DestinationRule("air"))
    assert (plan.matched, plan.skipped) == (1, 1) and not edit.dirty
    edit.apply(plan.change)
    assert edit.snapshot().block_nbt[(1, 0, 0)] == original
    assert edit.snapshot().block_nbt[(2, 0, 0)] == original
    edit.undo()
    assert not edit.dirty and (2, 0, 0) not in edit.snapshot().block_nbt


def test_filtered_take_keeps_skipped_source_after_rotation(edit, tmp_path):
    edit.apply(edit.set_block((3, 0, 0), "minecraft:gold_block"))
    clipboard = edit.copy(edit.select(((0, 0, 0), (2, 1, 1)))).transformed(turns=1)
    original = edit.snapshot().block_nbt[(1, 0, 0)]
    plan = plan_placement(edit, clipboard, ((3, 0, 0),), take=True, destination=DestinationRule("air"))
    assert (plan.matched, plan.skipped) == (1, 1)
    edit.apply(plan.change)
    assert edit.state_at((0, 0, 0)) == "minecraft:stone"
    assert edit.state_at((1, 0, 0)) == "minecraft:air"
    assert edit.state_at((3, 0, 0)) == "minecraft:gold_block"
    assert edit.state_at((3, 0, 1)) == "minecraft:chest[facing=east]"
    assert edit.snapshot().block_nbt[(3, 0, 1)] == original
    from structura_core import Structure
    assert Structure(edit.save(tmp_path / "filtered.nbt")).block_nbt[(3, 0, 1)] == original
    edit.undo()
    assert edit.snapshot().block_nbt[(1, 0, 0)] == original
    edit.redo()
    assert edit.state_at((3, 0, 1)) == "minecraft:chest[facing=east]"


def test_empty_match_does_not_resize_remove_or_add_history(edit):
    clipboard = edit.copy(edit.select(((1, 0, 0), (2, 1, 1))))
    plan = plan_placement(edit, clipboard, ((-3, 0, -3),), take=True,
                          destination=DestinationRule("material", "minecraft:stone"))
    assert plan.change.resize is None and not plan.change and plan.skipped == 1
    edit.apply(plan.change)
    assert not edit.dirty and not edit.can_undo and edit.size == (4, 2, 3)
    assert "No changes" in plan.summary


def test_overlapping_stack_matches_original_destinations(edit):
    selection = edit.select(((0, 0, 0), (2, 1, 1)))
    change = edit.stack(selection, 3, (1, 0, 0), destination=DestinationRule("material", "minecraft:chest"))
    edit.apply(change)
    assert edit.size == (4, 2, 3)
    assert [edit.state_at((x, 0, 0)) for x in range(4)] == [
        "minecraft:stone", "minecraft:stone", "minecraft:air", "minecraft:structure_void"]


def test_filtered_take_does_not_overwrite_a_skipped_source_with_another_cell(edit):
    clipboard = edit.copy(edit.select(((0, 0, 0), (2, 1, 1))))
    plan = plan_placement(edit, clipboard, ((1, 0, 0),), take=True,
                          destination=DestinationRule("material", "minecraft:chest"))
    assert plan.matched == 0 and plan.skipped == 2 and not plan.change
    edit.apply(plan.change)
    assert not edit.dirty and edit.state_at((0, 0, 0)) == "minecraft:stone"
    assert edit.snapshot().block_nbt[(1, 0, 0)]


def test_protected_source_propagates_through_an_overlapping_move_chain(edit):
    edit.apply(edit.set_block((1, 0, 0), "minecraft:stone"))
    edit.apply(edit.set_block((2, 0, 0), "minecraft:stone"))
    clipboard = edit.copy(edit.select(((0, 0, 0), (3, 1, 1))))
    plan = plan_placement(edit, clipboard, ((1, 0, 0),), take=True,
                          destination=DestinationRule("material", "minecraft:stone"))
    assert plan.skipped == 3 and not plan.change


def test_copy_air_obeys_destination_rule_even_for_omitted_cells(edit):
    clipboard = edit.copy(edit.select(((0, 1, 0), (2, 2, 1))))
    edit.apply(edit.paste(clipboard, (0, 0, 0), include_air=True,
                          destination=DestinationRule("material", "minecraft:stone")))
    assert edit.state_at((0, 0, 0)) == "minecraft:air"
    assert edit.state_at((1, 0, 0)) == "minecraft:chest[facing=north]"
    assert edit.snapshot().block_nbt[(1, 0, 0)]


def test_negative_keep_existing_placement_expands_and_restores(edit):
    clipboard = edit.copy(edit.select(((1, 0, 0), (2, 1, 1))))
    edit.apply(edit.paste(clipboard, (-1, -2, -3), destination=DestinationRule("air")))
    assert edit.origin == (-1, -2, -3) and edit.state_at((0, 0, 0)).startswith("minecraft:chest")
    edit.undo()
    assert edit.origin == (0, 0, 0) and not edit.dirty


@pytest.mark.parametrize("mode", ["air", "material"])
def test_missing_world_cells_are_not_treated_as_air(edit, mode):
    clipboard = edit.copy(edit.select(((0, 0, 0), (1, 1, 1))))
    edit.world_changes = object()
    edit.loaded_chunks = set()
    edit.loaded_sections = set()
    with pytest.raises(ValueError, match="absent chunks"):
        edit.paste(clipboard, (2, 0, 0), destination=DestinationRule(mode, "minecraft:stone"))
    edit.loaded_chunks = {(0, 0)}
    with pytest.raises(ValueError, match="absent section"):
        edit.paste(clipboard, (2, 0, 0), destination=DestinationRule(mode, "minecraft:stone"))
    assert not edit.dirty


def test_modded_ids_and_canonical_exact_states_need_no_registry():
    assert DestinationRule("material", "example:machine").allows("example:machine[active=true]")
    rule = DestinationRule("material", "example:machine[side=top,active=true]")
    assert rule.material == "example:machine[active=true,side=top]"
    assert rule.allows(rule.material) and not rule.allows("example:machine[active=true,side=bottom]")
    assert not rule.allows(None)


@pytest.mark.parametrize("mode,material", [("unknown", ""), ("material", ""), ("material", "bad id")])
def test_invalid_rules_are_rejected(mode, material):
    with pytest.raises(ValueError):
        DestinationRule(mode, material)
