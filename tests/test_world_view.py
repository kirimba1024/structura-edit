from types import SimpleNamespace

import pytest
from structura_core import Structure
from structura_core.world import WorldRegion

from structura_edit.world_view import WorldView


def test_world_view_exports_only_loaded_chunks_and_cannot_write_world(structure, tmp_path):
    structure.source_origin = (-16, 0, -16)
    region = WorldRegion(structure, frozenset(), frozenset({(-1, -1)}), (),
                         "minecraft:overworld", (-15, 1, -15), 0, 16)
    world = SimpleNamespace(path=tmp_path, dimensions={region.dimension: tmp_path}, name="Test")
    view = WorldView(world, region)
    assert view.readonly and view.origin == (-16, 0, -16)
    with pytest.raises(ValueError, match="view-only"):
        view.fill(view.select(), "minecraft:stone")
    with pytest.raises(ValueError, match="view-only"):
        view.save(tmp_path / "world.nbt")
    with pytest.raises(ValueError, match="absent"):
        view.export_selection(view.select(), tmp_path / "missing.nbt")
    assert not (tmp_path / "missing.nbt").exists()
    view.loaded_chunks = frozenset({(-1, -1)})
    exported = view.export_selection(view.select(), tmp_path / "complete.nbt")
    assert Structure(exported).present == structure.present
