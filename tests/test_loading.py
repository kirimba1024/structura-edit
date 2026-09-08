import pytest
from amulet_nbt import from_snbt
from structura_core import Structure

from structura_edit import EditSession

from structura_edit.loading import check_world_budget


def test_world_window_budget():
    check_world_budget((-1, -40, -1), 2, 32)
    with pytest.raises(ValueError, match="Reduce the radius"):
        check_world_budget((-1, -40, -1), 4, 192)


def test_sparse_schematic_with_large_bounds_is_rejected_before_rendering():
    pytest.importorskip("structura_render")
    from structura_edit.map_images import build_maps
    from structura_edit.sections import prepare_sections

    source = Structure.from_root(from_snbt('''{
        DataVersion:3955,size:[256,128,256],palette:[{Name:"minecraft:stone"}],
        blocks:[{pos:[0,0,0],state:0}],entities:[]
    }'''))
    edit = EditSession.from_structure(source)
    for build in (prepare_sections, build_maps):
        with pytest.raises(ValueError, match="split the schematic"):
            build(edit)
    assert edit.state_at((0, 0, 0)) == "minecraft:stone"
    assert not edit.dirty
