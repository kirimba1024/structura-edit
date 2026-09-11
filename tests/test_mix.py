from collections import Counter

import pytest

from structura_edit import Mix


def test_fill_with_mix_is_deterministic(edit):
    mix = Mix((("minecraft:stone", 3), ("minecraft:dirt", 1)), seed=7)
    first = edit.fill(edit.select(), mix)
    second = edit.fill(edit.select(), mix)
    assert {delta.position: delta.after.state for delta in first.changes} == {
        delta.position: delta.after.state for delta in second.changes}
    assert edit.apply(first) == 23
    assert edit.state_at((0, 0, 0)) in ("minecraft:stone", "minecraft:dirt")


def test_mix_preview_matches_apply(edit):
    mix = Mix((("minecraft:stone", 1), ("minecraft:cobblestone", 2)), seed=42)
    change = edit.fill(edit.select(), mix)
    preview = {delta.position: delta.after.state for delta in change.changes}
    edit.apply(change)
    assert {position: edit.state_at(position) for position in preview} == preview


def test_mix_weights_distribute_relative():
    mix = Mix((("minecraft:stone", 1), ("minecraft:dirt", 1), ("minecraft:andesite", 2)), seed=3)
    counts = Counter(mix.at((x, 0, z)) for x in range(200) for z in range(150))
    assert abs(counts["minecraft:stone"] - 7500) < 750
    assert abs(counts["minecraft:dirt"] - 7500) < 750
    assert abs(counts["minecraft:andesite"] - 15000) < 1500


def test_mix_seed_changes_outcome():
    first = Mix((("minecraft:stone", 1), ("minecraft:dirt", 1)), seed=1)
    second = Mix((("minecraft:stone", 1), ("minecraft:dirt", 1)), seed=2)
    assert any(first.at((x, 0, 0)) != second.at((x, 0, 0)) for x in range(64))


def test_mix_validation_and_canonicalization():
    with pytest.raises(ValueError):
        Mix(())
    with pytest.raises(ValueError):
        Mix((("minecraft:stone", 0),))
    with pytest.raises(ValueError):
        Mix((("minecraft:stone", True),))
    with pytest.raises(ValueError):
        Mix((("minecraft:stone", 1),), seed=-1)
    assert Mix((("minecraft:oak_stairs[facing=north]", 2),)).items == (("minecraft:oak_stairs[facing=north]", 2),)
    assert Mix((("minecraft:stone", 1),)).label == "1 materials · seed 0 · local"


def test_replace_with_mix_preserves_properties(edit):
    edit.apply(edit.fill(edit.select(), "minecraft:oak_stairs[facing=north,half=top]"))
    mix = Mix((("minecraft:spruce_stairs", 1),), seed=5)
    change = edit.replace(edit.select(), "minecraft:oak_stairs", mix, preserve_properties=True)
    states = {delta.after.state for delta in change.changes}
    assert states == {"minecraft:spruce_stairs[facing=north,half=top]"}
