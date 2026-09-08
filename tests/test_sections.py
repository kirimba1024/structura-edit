import json
from collections import Counter

import numpy as np
import pytest
from amulet_nbt import from_snbt
from structura_core import Structure

from structura_edit import EditSession
from structura_edit.sections import prepare_sections


@pytest.fixture
def assets(tmp_path):
    pytest.importorskip("structura_render")
    from PIL import Image

    for directory in ("blockstates", "models/block", "textures/block", "textures/entity/decorated_pot"):
        (tmp_path / directory).mkdir(parents=True)
    for name, color in (("stone", "grey"), ("oak_planks", "brown"), ("water_still", "blue"),
                        ("water_flow", "cyan"), ("glass", (200, 220, 240, 100))):
        Image.new("RGBA", (16, 16), color).save(tmp_path / f"textures/block/{name}.png")
    directions = ("up", "down", "north", "south", "east", "west")
    for name in ("stone", "glass", "oak_stairs"):
        (tmp_path / f"blockstates/{name}.json").write_text(json.dumps({"variants": {"": {"model": f"block/{name}"}}}))
        boxes = [([0, 0, 0], [16, 16, 16])] if name != "oak_stairs" else [([0, 0, 0], [16, 8, 16]), ([0, 8, 8], [16, 16, 16])]
        faces = {direction: dict(texture="#all", cullface=direction) for direction in directions}
        elements = [{"from": lower, "to": upper, "faces": faces} for lower, upper in boxes]
        model = dict(textures={"all": f"block/{'oak_planks' if name == 'oak_stairs' else name}"}, elements=elements)
        (tmp_path / f"models/block/{name}.json").write_text(json.dumps(model))
    for name, color in (("decorated_pot_side", "brown"), ("decorated_pot_base", "grey"),
                        ("angler_pottery_pattern", "red"), ("archer_pottery_pattern", "blue")):
        Image.new("RGBA", (32, 32), color).save(tmp_path / f"textures/entity/decorated_pot/{name}.png")
    return str(tmp_path)


def sample(name="stone"):
    source = Structure.from_root(from_snbt('''{
        DataVersion:3955,size:[48,3,3],palette:[{Name:"minecraft:%s"},{Name:"minecraft:stone"}],
        blocks:[{pos:[15,1,1],state:0},{pos:[16,1,1],state:0},{pos:[34,1,1],state:1}],
        entities:[{pos:[15.75d,1d,1.5d],blockPos:[15,1,1],nbt:{id:"minecraft:tnt"}}]
    }''' % name))
    if name == "decorated_pot":
        source.block_nbt = {position: from_snbt('{sherds:["minecraft:%s_pottery_sherd","minecraft:%s_pottery_sherd","minecraft:%s_pottery_sherd","minecraft:%s_pottery_sherd"]}' % ((pattern,) * 4))
                            for position, pattern in (((15, 1, 1), "angler"), ((16, 1, 1), "archer"))}
    return EditSession.from_structure(source)


def surfaces(data):
    groups = []
    for mesh in data["meshes"]:
        uv = mesh.uv[mesh.quads].mean(axis=1)
        x = np.clip((uv[:, 0] * mesh.image.shape[1]).astype(int), 0, mesh.image.shape[1] - 1)
        y = np.clip(((1 - uv[:, 1]) * mesh.image.shape[0]).astype(int), 0, mesh.image.shape[0] - 1)
        groups.append((mesh.points[mesh.quads], mesh.image[y, x]))
    for points, faces, color in data["flat"]:
        quads = points[faces.reshape(-1, 5)[:, 1:]]
        groups.append((quads, np.broadcast_to(color, (len(quads), 4))))
    result = Counter()
    for quads, colors in groups:
        for quad, color in zip(quads, colors):
            cross = np.cross(quad[1] - quad[0], quad[2] - quad[0]) + np.cross(quad[2] - quad[0], quad[3] - quad[0])
            area = np.linalg.norm(cross) / 2
            if area:
                normal = cross / (2 * area)
                plane = tuple(np.round(normal, 5)), round(float(quad[0] @ normal), 5)
                result[plane, tuple(color)] += float(area)
    return result


def combined(sections):
    return sum((surfaces(section) for section in sections.values()), Counter())


@pytest.mark.parametrize("name", ["stone", "glass", "water", "oak_fence", "oak_stairs", "decorated_pot"])
def test_section_seams_preserve_surface_area_materials_and_nbt(assets, name):
    from structura_edit.preview import build_preview, build_sections

    edit = sample(name)
    expected = build_preview(edit, assets=assets)
    actual = build_sections(**prepare_sections(edit), assets=assets)
    assert combined(actual["sections"]) == pytest.approx(surfaces(expected))
    assert edit.snapshot().block_nbt == edit._document.source.block_nbt


@pytest.mark.parametrize("destination", [(-20, -2, -3), (50, 6, 4)])
def test_expanded_placement_and_ghost_keep_all_sections(assets, destination):
    from structura_edit.preview import build_preview, build_sections

    edit = sample()
    clipboard = edit.copy(edit.select(((15, 1, 1), (17, 2, 2))))
    change = edit.paste(clipboard, destination, take=True)
    expected = surfaces(build_preview(edit, change, assets=assets))
    prepared = prepare_sections(edit, change, previous=(edit, None))
    assert prepared["reset"]
    actual = build_sections(**prepared, assets=assets)
    assert combined(actual["sections"]) == pytest.approx(expected)
    preview = build_sections(**prepare_sections(edit, change, ghost=change), assets=assets)
    visible = combined(preview["sections"])
    for section in preview["sections"].values():
        if "added" in section["layers"]:
            visible += surfaces(section["layers"]["added"])
    assert visible == pytest.approx(expected)
    assert prepare_sections(edit, previous=(edit, change))["reset"]


@pytest.mark.parametrize("name", ["stone", "glass", "water", "oak_fence", "oak_stairs", "decorated_pot"])
def test_ghost_partition_preserves_final_geometry_and_neighbor_connections(assets, name):
    from structura_edit.preview import build_preview, build_sections

    edit = sample(name)
    branch = edit.fork()
    branch.apply(branch.set_block((14, 1, 1), f"minecraft:{name}"))
    branch.apply(branch.set_block((15, 1, 1), "minecraft:air"))
    change = edit.diff(branch)
    result = build_sections(**prepare_sections(edit, change, ghost=change), assets=assets)
    actual = combined(result["sections"])
    for section in result["sections"].values():
        if "added" in section["layers"]:
            actual += surfaces(section["layers"]["added"])
    assert actual == pytest.approx(surfaces(build_preview(edit, change, assets=assets)))
    assert any(section["layers"].get("removed") for section in result["sections"].values())
    assert edit.state_at((15, 1, 1)) == f"minecraft:{name}"


def test_boundary_preview_discard_apply_undo_and_redo_keep_distant_geometry(tmp_path):
    pytest.importorskip("structura_render")
    from structura_edit.preview import build_preview, build_sections

    assets, edit = str(tmp_path), sample()
    displayed = (edit.fork(), None)
    sections = build_sections(**prepare_sections(edit), assets=assets)["sections"]
    original = combined(sections)
    distant = sections[(2, 0, 0)]
    entities = sections["entities"]

    def update(change=None):
        nonlocal displayed
        request = prepare_sections(edit, change, previous=displayed)
        result = build_sections(**request, assets=assets)
        sections.update(result["sections"])
        displayed = edit.fork(), change
        assert sections[(2, 0, 0)] is distant and sections["entities"] is entities
        assert combined(sections) == pytest.approx(surfaces(build_preview(edit, change, assets=assets)))

    change = edit.set_block((15, 1, 1), "minecraft:air")
    update(change)
    assert combined(sections) != original
    update()
    assert combined(sections) == original
    update(change)
    edit.apply(change)
    assert not prepare_sections(edit, previous=displayed)["sections"]
    assert edit.undo()
    update()
    assert combined(sections) == original
    assert edit.redo()
    update()


def test_entity_toggle_keeps_block_sections_and_entities_outside_bounds(tmp_path):
    pytest.importorskip("structura_render")
    from structura_edit.preview import build_preview, build_sections

    edit = sample()
    edit._document.source.entities[0]["pos"] = from_snbt("[50.75d,1d,1.5d]")
    sections = build_sections(**prepare_sections(edit), assets=str(tmp_path))["sections"]
    assert combined(sections) == pytest.approx(surfaces(build_preview(edit, assets=str(tmp_path))))
    blocks = sections[(0, 0, 0)]
    request = prepare_sections(edit, previous=(edit.fork(), None), include_entities=False)
    sections.update(build_sections(**request, assets=str(tmp_path))["sections"])
    assert sections[(0, 0, 0)] is blocks
    assert combined(sections) == pytest.approx(surfaces(build_preview(edit, assets=str(tmp_path), include_entities=False)))


def test_corner_edit_updates_all_touching_sections(tmp_path):
    pytest.importorskip("structura_render")
    from structura_edit.preview import build_preview, build_sections

    source = Structure.from_root(from_snbt('''{
        DataVersion:3955,size:[32,32,32],palette:[{Name:"minecraft:stone"}],
        blocks:[],entities:[]
    }'''))
    source.present = {(x, y, z): 0 for x in (15, 16) for y in (15, 16) for z in (15, 16)}
    edit = EditSession.from_structure(source)
    sections = build_sections(**prepare_sections(edit), assets=str(tmp_path))["sections"]
    before = edit.fork()
    edit.apply(edit.set_block((15, 15, 15), "minecraft:air"))
    sections.update(build_sections(**prepare_sections(edit, previous=(before, None)), assets=str(tmp_path))["sections"])
    assert combined(sections) == pytest.approx(surfaces(build_preview(edit, assets=str(tmp_path))))


def test_skipped_revisions_and_replaced_previews_restore_the_visible_state(tmp_path):
    pytest.importorskip("structura_render")
    from structura_edit.preview import build_preview, build_sections

    edit, assets = sample(), str(tmp_path)
    before = edit.fork(), None
    sections = build_sections(**prepare_sections(edit), assets=assets)["sections"]
    for position in ((8, 1, 1), (34, 1, 1)):
        edit.apply(edit.set_block(position, "minecraft:glass"))
    sections.update(build_sections(**prepare_sections(edit, previous=before), assets=assets)["sections"])
    assert combined(sections) == pytest.approx(surfaces(build_preview(edit, assets=assets)))
    before = edit.fork(), None
    first = edit.set_block((15, 1, 1), "minecraft:air")
    second = edit.set_block((34, 1, 1), "minecraft:gold_block")
    for change in (first, second, None):
        sections.update(build_sections(**prepare_sections(edit, change, previous=before), assets=assets)["sections"])
        assert combined(sections) == pytest.approx(surfaces(build_preview(edit, change, assets=assets)))
        before = edit.fork(), change


def test_height_changes_rebuild_cut_faces_and_keep_distant_sections(assets):
    from structura_edit.height_slice import HeightSlice
    from structura_edit.preview import build_geometry, build_sections
    from structura_edit.render_source import RenderSource

    source = Structure.from_root(from_snbt('''{
        DataVersion:3955,size:[3,64,3],palette:[{Name:"minecraft:stone"}],blocks:[],entities:[]
    }'''))
    source.present = {(x, y, z): 0 for x in range(3) for y in range(64) for z in range(3)}
    edit = EditSession.from_structure(source)
    previous = HeightSlice()
    sections = build_sections(**prepare_sections(edit), assets=assets)["sections"]
    for height in (HeightSlice("below", 47), HeightSlice("below", 46), HeightSlice("below", 16),
                   HeightSlice("below", 15), HeightSlice("layer", 15), HeightSlice("layer", -10), HeightSlice()):
        prepared = prepare_sections(edit, height=height, previous_height=previous, previous=(edit, None))
        if previous == HeightSlice("below", 47) and height == HeightSlice("below", 46):
            assert set(prepared["sections"]) == {(0, 2, 0), "entities"}
        sections.update(build_sections(**prepared, assets=assets)["sections"])
        expected = build_geometry(RenderSource(edit, height).region(), assets)
        assert combined(sections) == pytest.approx(surfaces(expected))
        previous = height
    assert not edit.dirty and not edit.can_undo


def test_height_slice_applies_to_removed_ghosts_and_expanded_placement(assets):
    from structura_edit.height_slice import HeightSlice
    from structura_edit.placement import Placement
    from structura_edit.placement_jobs import prepare_placement
    from structura_edit.preview import build_geometry, build_sections
    from structura_edit.render_source import RenderSource, preview_session

    edit = sample()
    height = HeightSlice("below", 1)
    change = edit.set_block((15, 1, 1), "minecraft:air")
    result = build_sections(**prepare_sections(edit, change, ghost=change, height=height), assets=assets)
    assert any(section["layers"].get("removed") for section in result["sections"].values())
    hidden = build_sections(**prepare_sections(edit, change, ghost=change, height=HeightSlice("layer", 0)), assets=assets)
    assert not any(section["layers"] for section in hidden["sections"].values())
    clipboard = edit.copy(edit.select(((15, 1, 1), (17, 2, 2))))
    placement = Placement(clipboard, (-2, -3, 0))
    change, rendered = prepare_placement(edit, placement, height=height, assets=assets, section_bytes={})
    assert rendered["reset"]
    expected = build_geometry(RenderSource(preview_session(edit, change), height).region(include_entities=True), assets)
    assert combined(rendered["sections"]) == pytest.approx(surfaces(expected))
