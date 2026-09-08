from types import SimpleNamespace

import pytest
from structura_core import Structure
from structura_core.world import WorldRegion

from structura_edit.world_view import WorldView


def test_world_view_exports_and_edits_only_loaded_chunks(structure, tmp_path):
    structure.source_origin = (-16, 0, -16)
    region = WorldRegion(structure, frozenset(), frozenset({(-1, -1)}), (),
                         "minecraft:overworld", (-15, 1, -15), 0, 16)
    world = SimpleNamespace(path=tmp_path, dimensions={region.dimension: tmp_path}, name="Test")
    view = WorldView(world, region)
    assert not view.readonly and view.origin == (-16, 0, -16)
    with pytest.raises(ValueError, match="absent"):
        view.apply(view.fill(view.select(), "minecraft:gold_block"))
    with pytest.raises(ValueError, match="Use Export"):
        view.save(tmp_path / "world.nbt")
    with pytest.raises(ValueError, match="absent"):
        view.export_selection(view.select(), tmp_path / "missing.nbt")
    assert not (tmp_path / "missing.nbt").exists()
    view.loaded_chunks = frozenset({(-1, -1)})
    exported = view.export_selection(view.select(), tmp_path / "complete.nbt")
    assert Structure(exported).present == structure.present


def test_world_patch_and_history_survive_another_loaded_area(structure, tmp_path):
    world = SimpleNamespace(path=tmp_path, dimensions={"minecraft:overworld": tmp_path}, name="Test")
    def region(origin):
        from copy import deepcopy

        source = deepcopy(structure)
        source.source_origin = origin
        return WorldRegion(source, frozenset({(origin[0] // 16, origin[2] // 16)}), frozenset(), (),
                           "minecraft:overworld", origin, 0, 16)
    first = WorldView(world, region((0, 0, 0)))
    first.apply(first.fill(first.select(((0, 0, 0), (1, 1, 1))), "minecraft:gold_block"))
    second = WorldView(world, region((32, 0, 0)), first.world_changes)
    second.apply(second.fill(second.select(((0, 0, 0), (1, 1, 1))), "minecraft:diamond_block"))
    assert len(second.world_changes.patch) == 2
    assert second.undo() and second.state_at((0, 0, 0)) == "minecraft:stone"
    assert second.undo() and not second.dirty
    assert second.redo() and second.redo()
    refreshed = WorldView(world, region((0, 0, 0)), second.world_changes)
    assert refreshed.state_at((0, 0, 0)) == "minecraft:gold_block" and len(refreshed.history.entries) == 2
    empty = (0, 1, 1)
    refreshed.apply(refreshed.set_block(empty, "minecraft:gold_block"))
    with refreshed.transaction("Remove added block") as branch:
        branch.apply(branch.set_block(empty, "minecraft:air"))
    assert refreshed.state_at(empty) == "minecraft:air" and len(refreshed.world_changes.patch) == 2
    assert refreshed.undo() and refreshed.state_at(empty) == "minecraft:gold_block"
    assert not list(tmp_path.iterdir())
