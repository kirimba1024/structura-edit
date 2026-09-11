import json
from dataclasses import replace

import pytest
from amulet_nbt import from_snbt
from structura_core import Structure
from structura_core.schematic import Schematic

from structura_edit import CellSet, Condition, EditSession, Mix
from structura_edit.change_report import report_change
from structura_edit.height_slice import HeightSlice
from structura_edit.material_catalog import material_catalog
from structura_edit.paint import paint_stroke
from structura_edit.planar import extrude, frame, planar_selection
from structura_edit.selection_export import export_losses


def plane():
    source = Structure.from_root(from_snbt('{DataVersion:3955,size:[9,4,11],palette:[{Name:"minecraft:air"}],blocks:[],entities:[]}'))
    session = EditSession.from_structure(source)
    selected = session.select(((2, 0, 2), (7, 1, 9)))
    session.apply(session.fill(selected, 'minecraft:stone'))
    return session, selected


def test_conditions_share_coordinates_and_nbt_in_all_roles(edit):
    condition = Condition('all', (Condition('non-air'), Condition('block-entities', negate=True), Condition('height', ('0', '0'))))
    assert {d.position for d in edit.replace(edit.select(), condition, 'minecraft:gold_block').changes} == {(0, 0, 0)}
    assert {d.position for d in edit.shape(edit.select(), 'minecraft:gold_block', mask=condition).changes} == {(0, 0, 0)}
    from structura_edit import DestinationRule
    clip = edit.copy(edit.select(((0, 0, 0), (1, 1, 1))))
    assert not edit.paste(clip, (1, 0, 0), destination=DestinationRule('where', condition=condition))
    assert not condition.matches('minecraft:stone', position=(0, 0, 0), known=False)
    assert not Condition('air', negate=True).matches(None, known=False)
    assert not Condition('properties', ('facing=north',), strict=True).matches('minecraft:stone')
    assert Condition('any', (Condition('air'), Condition('materials', ('minecraft:stone',)))).matches(None)
    implicit = edit.replace(edit.select(), Condition('air'), 'minecraft:gold_block')
    assert (0, 1, 2) in implicit.positions


def test_world_mix_is_invariant_to_document_origin_and_roundtrips_preset():
    mix = Mix((('minecraft:stone', 3), ('minecraft:gold_block', 1)), seed=73, anchor='world')
    assert mix.at((1, 2, 3), (16, -16, 32)) == mix.at((17, -14, 35))
    assert Mix.from_preset(json.loads(json.dumps(mix.preset()))) == mix
    gradient = replace(mix, gradient=(-10, 10))
    assert gradient.at((2, -10, 3)) == 'minecraft:stone'
    assert gradient.at((2, 10, 3)) == 'minecraft:gold_block'
    with pytest.raises(ValueError):
        Mix.from_preset(dict(mix.preset(), algorithm=2))


def test_mix_applies_world_coordinates_in_session(edit):
    mix = Mix((('minecraft:stone', 1), ('minecraft:gold_block', 1)), seed=5, anchor='world')
    edit._document.origin = (100, 0, -100)
    change = edit.fill(edit.select(), mix)
    assert all(d.after.state == mix.at(d.position, edit.origin) for d in change.changes)


def test_reports_include_nbt_and_hidden_changes(edit):
    change = edit.fill(edit.select(((0, 0, 0), (2, 1, 1))), 'minecraft:air')
    report = report_change(edit, change, HeightSlice('layer', 1))
    assert (report.removed, report.removed_data, report.hidden) == (2, 1, 2)
    assert report.block_data == 1


def test_selection_sponge_roundtrip_retains_states_nbt_entities(edit, tmp_path):
    selected = edit.select(((1, 0, 0), (4, 2, 3)))
    path = tmp_path / 'selection.schem'
    losses = export_losses(edit, selected, path)
    assert any('omitted' in loss for loss in losses)
    edit.export_selection(selected, path)
    schematic = Schematic(path)
    output = schematic.to_structure()
    assert schematic.offset == (0, 0, 0) and output.size == (3, 2, 3)
    assert output.block_nbt[(0, 0, 0)]['Items'] == edit.snapshot().block_nbt[(1, 0, 0)]['Items']
    assert str(output.palette_raw[output.present[(0, 0, 0)]]['Properties']['facing']) == 'north'
    assert tuple(float(v) for v in output.entities[0]['pos']) == (0.5, 1, 1.5)


def test_sparse_sponge_footprint_becomes_air(edit, tmp_path):
    selected = CellSet.from_positions(((0, 0, 0), (2, 0, 0)))
    path = edit.export_selection(selected, tmp_path / 'sparse.schem')
    output = Schematic(path).to_structure()
    assert output.name_at((1, 0, 0)) == 'minecraft:air'
    assert not output.block_nbt


def test_resource_catalog_discovers_new_material_and_english_name(tmp_path):
    import zipfile
    jar = tmp_path / 'client.jar'
    with zipfile.ZipFile(jar, 'w') as archive:
        archive.writestr('version.json', '{"world_version":3955}')
        archive.writestr('assets/minecraft/blockstates/diamond_block.json', '{}')
        archive.writestr('assets/minecraft/lang/en_us.json', '{"block.minecraft.diamond_block":"Block of Diamond"}')
    result = material_catalog(jar)
    assert result['version'] == 3955
    assert result['rows'] == {'minecraft:diamond_block': 'Block of Diamond'}


def test_planar_four_connectivity_extrude_and_single_undo():
    session, selected = plane()
    cells = planar_selection(session, (2, 0, 2), (0, 1, 0))
    assert cells.volume == 35 and set(cells.positions()) == set(selected.positions())
    before = session.snapshot().present.copy()
    change = extrude(session, cells, (0, 1, 0), 2)
    assert len(change.changes) == 70
    session.apply(change)
    assert session.state_at((2, 2, 2)) == 'minecraft:stone'
    assert session.undo()
    assert session.snapshot().present == before
    with pytest.raises(ValueError, match='occupied'):
        extrude(session, session.select(((2, 0, 2), (3, 1, 3))), (1, 0, 0), 1)


def test_frame_linf_counts_and_excludes_stairs_or_nbt(edit):
    session, selected = plane()
    assert len(frame(session, selected, (0, 1, 0), 'minecraft:gold_block').changes) == 28
    assert len(frame(session, selected, (0, 1, 0), 'minecraft:gold_block', outside=False).changes) == 20
    with pytest.raises(ValueError, match='full cube'):
        planar_selection(edit, (1, 0, 0), (0, 1, 0))
    with pytest.raises(ValueError, match='full cube'):
        frame(session, selected, (0, 1, 0), 'minecraft:oak_stairs')


def test_paint_is_independent_of_straight_path_sampling_and_non_accumulating():
    session, selected = plane()
    coarse = [(2.5, 0.5, 2.5), (6.5, 0.5, 8.5)]
    fine = [(2.5 + 4 * i / 20, 0.5, 2.5 + 6 * i / 20) for i in range(21)]
    a = paint_stroke(session, selected, coarse, 'minecraft:gold_block', 1)
    b = paint_stroke(session, selected, fine, 'minecraft:gold_block', 1)
    repeated = paint_stroke(session, selected, [*coarse, *reversed(coarse)], 'minecraft:gold_block', 1)
    assert a.positions == b.positions == repeated.positions
    assert len(set(a.positions)) == len(a.changes)
    session.apply(a)
    assert session.undo() and all(session.state_at(p) == 'minecraft:stone' for p in selected.positions())
    disconnected = paint_stroke(session, selected, [coarse[0], None, coarse[-1]], 'minecraft:gold_block', 0.1)
    assert len(disconnected.changes) == 2
    with pytest.raises(ValueError, match='4096'):
        paint_stroke(session, selected, [coarse[0]] * 4097, 'minecraft:gold_block')


def test_export_opens_in_independent_amulet_reader(edit, tmp_path):
    amulet = pytest.importorskip('amulet')
    path = edit.export_selection(edit.select(), tmp_path / 'independent.schem')
    wrapper = amulet.load_format(str(path))
    wrapper.open()
    try:
        raw = wrapper.get_raw_chunk_data(0, 0, wrapper.dimensions[0])
        assert raw.palette[raw.blocks[0, 0, 0]].namespaced_name == 'minecraft:stone'
        assert raw.palette[raw.blocks[1, 0, 0]].namespaced_name == 'minecraft:chest'
        assert len(raw.block_entities) == 1 and len(raw.entities) == 1
    finally:
        wrapper.close()


def test_report_recounts_when_view_slice_changes(edit):
    report = report_change(edit, edit.fill(edit.select(), 'minecraft:gold_block'))
    layer = report.for_height(HeightSlice('layer', 0))
    assert layer.hidden == edit.size[0] * edit.size[2]
    assert layer.for_height(HeightSlice()).hidden == 0


def test_unknown_cells_never_match_negated_conditions(world_edit):
    world_edit.loaded_chunks = frozenset()
    assert not Condition('block-entities', negate=True).at(world_edit, (0, 0, 0))


def test_extrude_rejects_overridden_shape_states():
    session, selected = plane()
    session.apply(session.fill(selected, 'minecraft:piston[extended=true,facing=up]'))
    with pytest.raises(ValueError, match='default-state'):
        extrude(session, selected, (0, 1, 0), 1)


def test_repeat_worker_reports_slice_without_passing_view_options_to_algorithm(edit):
    from structura_edit.tasks import execute

    plan = execute('repeat', dict(session=edit, selection=edit.select(((0, 0, 0), (1, 1, 1))),
                                  copies=1, step=(0, 1, 0), height=HeightSlice('layer', 0)))
    assert len(plan.change.changes) == 1 and plan.change.report.hidden == 1
    assert not edit.dirty
