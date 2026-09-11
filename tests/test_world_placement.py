from pathlib import Path

import pytest

from smoke_world_edit import create_world
from structura_edit.placement import Placement
from structura_edit.source_loading import open_source
from structura_edit.world_placement import load_placement_area, placement_area


def local(session, position):
    return tuple(p - o for p, o in zip(position, session.origin))


@pytest.fixture
def world(tmp_path):
    create_world(tmp_path)
    return open_source(tmp_path, center=(8, 8, 8), radius=0)


def test_take_loads_destination_and_preserves_changes_history_and_coordinates(world):
    world.apply(world.set_block(local(world, (2, 0, 2)), "minecraft:gold_block"))
    selection = world.select((local(world, (1, 0, 1)), local(world, (3, 1, 3))))
    placement = Placement(world.copy(selection), local(world, (35, 1, 1)), take=True)
    original = (Path(world.path) / "region/r.0.0.mca").read_bytes()
    assert placement.reason(world) == ""
    loaded, moved = load_placement_area(world, placement)
    assert loaded._id == world._id and loaded.dirty and loaded.can_undo
    assert (2, 0) in loaded.loaded_chunks
    assert moved.clipboard.can_take_from(loaded)
    assert moved.position == local(loaded, (35, 1, 1))
    plan = moved.plan(loaded)
    loaded.apply(plan.change)
    assert len(loaded.history.entries) == 2
    assert loaded.state_at(local(loaded, (2, 0, 2))) == "minecraft:air"
    assert loaded.state_at(local(loaded, (36, 1, 2))) == "minecraft:gold_block"
    assert (Path(world.path) / "region/r.0.0.mca").read_bytes() == original
    loaded.undo()
    assert loaded.state_at(local(loaded, (2, 0, 2))) == "minecraft:gold_block"
    loaded.undo()
    assert not loaded.dirty
    assert world.dirty and len(world.history.entries) == 1


def test_missing_destination_does_not_become_empty_generated_world(world):
    selection = world.select((local(world, (1, 0, 1)), local(world, (2, 1, 2))))
    placement = Placement(world.copy(selection), local(world, (20, 1, 1)))
    loaded, moved = load_placement_area(world, placement)
    with pytest.raises(ValueError, match="absent chunks"):
        moved.plan(loaded)
    assert not loaded.dirty and not world.dirty


def test_distant_placement_is_bounded_before_reading(world):
    with pytest.raises(ValueError, match="Too far"):
        placement_area(world, (10000, 0, 10000), (1, 1, 1))
    assert placement_area(world, (0, 0, 0), (1, 1, 1)) is None


def test_stale_take_is_rejected_before_rebasing(world):
    selection = world.select((local(world, (1, 0, 1)), local(world, (2, 1, 2))))
    placement = Placement(world.copy(selection), local(world, (35, 1, 1)), take=True)
    world.apply(world.set_block(local(world, (1, 0, 1)), "minecraft:gold_block"))
    with pytest.raises(ValueError, match="copied blocks changed"):
        load_placement_area(world, placement)
