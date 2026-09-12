from overview_fixture import create_overview_world

from structura_edit.render_source import RenderSource
from structura_edit.source_loading import open_source
from structura_edit.sections import prepare_sections


def test_neighbor_halo_does_not_change_editable_bounds_or_exported_data(tmp_path):
    world = create_overview_world(tmp_path / "world")
    before = {p: p.read_bytes() for p in world.rglob("*") if p.is_file()}
    session = open_source(world, center=(8, 8, 8), radius=0, vertical_radius=None, include_entities=False)
    assert session.size == (16, 16, 16) and session.origin == (0, 0, 0)
    render = RenderSource(session)
    source = render.region((-1, -1, -1), (17, 17, 17))
    assert source.palette[source.present[(0, 5, 1)]] == "minecraft:grass_block"
    assert source.palette[source.present[(17, 5, 1)]] == "minecraft:grass_block"
    assert source.present.get((1, 0, 1)) is None
    assert render.region().size == session.snapshot().size == session.size
    assert len(render.region().present) == len(session.snapshot().present)
    assert before == {p: p.read_bytes() for p in before}


def test_neighbor_halo_includes_unsaved_changes_outside_current_area(tmp_path):
    world = create_overview_world(tmp_path / "world")
    wide = open_source(world, center=(8, 8, 8), radius=1, vertical_radius=None, include_entities=False)
    position = tuple(p - o for p, o in zip((16, 4, 0), wide.origin))
    wide.apply(wide.set_block(position, "minecraft:gold_block"))
    small = open_source(world, center=(8, 8, 8), radius=0, vertical_radius=None, include_entities=False,
                        world_changes=wide.world_changes)
    source = RenderSource(small).region((-1, -1, -1), (17, 17, 17))
    assert source.palette[source.present[(17, 5, 1)]] == "minecraft:gold_block"
    assert small.size == (16, 16, 16) and not small._cells
    shown = small.fork()
    assert small.undo()
    assert (0, 0, 0) in prepare_sections(small, previous=(shown, None))["sections"]
    source = RenderSource(small).region((-1, -1, -1), (17, 17, 17))
    assert source.palette[source.present[(17, 5, 1)]] == "minecraft:grass_block"
    previous = RenderSource(shown).region((-1, -1, -1), (17, 17, 17))
    assert previous.palette[previous.present[(17, 5, 1)]] == "minecraft:gold_block"
    assert small.redo()
    small.save()
    assert not small.dirty
    source = RenderSource(small).region((-1, -1, -1), (17, 17, 17))
    assert source.palette[source.present[(17, 5, 1)]] == "minecraft:gold_block"
    assert small.undo()
    source = RenderSource(small).region((-1, -1, -1), (17, 17, 17))
    assert source.palette[source.present[(17, 5, 1)]] == "minecraft:grass_block"
