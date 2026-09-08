from types import SimpleNamespace

import pytest

from structura_edit.height_slice import HeightSlice
from structura_edit.picking import pick_block
from structura_edit.render_source import RenderSource
from structura_edit.view_pipeline import ViewRequest


@pytest.mark.parametrize("mode,y,expected", [
    ("all", 0, (0, 48)), ("below", -50, (0, 15)), ("layer", -50, (14, 15)),
    ("below", -100, (0, 0)), ("layer", -100, (0, 0)), ("layer", 100, (48, 48)),
])
def test_world_height_is_clamped_to_loaded_interval(mode, y, expected):
    session = SimpleNamespace(origin=(16, -64, -16), size=(16, 48, 16))
    assert HeightSlice(mode, y).interval(session) == expected


def test_picking_enters_cut_surface_and_handles_an_empty_slice(edit):
    edit.apply(edit.set_block((0, 1, 0), "minecraft:gold_block"))
    ray = (0.5, 10, 0.5), (0, -1, 0)
    assert pick_block(edit, *ray).position == (0, 1, 0)
    hit = pick_block(edit, *ray, height=HeightSlice("below", 0))
    assert hit.position == (0, 0, 0) and hit.normal == (0, 1, 0)
    assert pick_block(edit, *ray, height=HeightSlice("layer", 50)) is None
    assert pick_block(edit, (0.5, 0, 0.5), (0, 1, 0), HeightSlice("layer", 1)).normal == (0, -1, 0)
    assert pick_block(edit, (-1, 1.5, 0.5), (1, 0, 0), HeightSlice("below", 0)) is None


def test_maps_blocks_and_entity_anchors_share_visibility_without_mutation(edit):
    source = edit._document.source
    snapshot = source.present.copy(), source.block_nbt.copy(), edit._entities.copy(), edit.revision
    hidden = RenderSource(edit, HeightSlice("below", 0))
    visible = RenderSource(edit, HeightSlice("layer", 1))
    assert not hidden.entity_records() and len(visible.entity_records()) == 1
    assert not visible.region().present
    assert hidden.region().block_nbt == source.block_nbt
    edit.map_identity = "fixture"
    for height in (HeightSlice("below", 0), HeightSlice("layer", 1)):
        request = ViewRequest(edit, None, None, True, False, height)
        args = request.map_args("unused.sqlite")
        assert args["source"].present == RenderSource(edit, height).region().present
        assert args["atlas"] is None and not args["source"].block_nbt
    assert snapshot == (source.present, source.block_nbt, edit._entities, edit.revision)
    assert not edit.dirty and not edit.can_undo


def test_cut_height_keeps_world_coordinates_after_negative_expansion(edit):
    height = HeightSlice("below", 0)
    edit.apply(edit.paste(edit.copy(edit.select(((0, 0, 0), (1, 1, 1)))), (0, -4, 0)))
    assert edit.origin[1] == -4 and height.interval(edit) == (0, 5)
    assert all(p[1] + edit.origin[1] <= 0 for p in RenderSource(edit, height).region().present)
