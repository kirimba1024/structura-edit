from dataclasses import replace

import pytest
from amulet_nbt import from_snbt
from structura_core import Structure
from structura_core.entity_positions import shift_entity
from structura_core.world_entities import EntityLocation

from structura_edit import DestinationRule, EditSession
from structura_edit.clipboard_placement import plan_placement
from structura_edit.entity_transform import payloads


@pytest.fixture
def scene():
    return EditSession.from_structure(Structure.from_root(from_snbt('''{
        DataVersion:3955,size:[8,8,8],palette:[{Name:"minecraft:chest",Properties:{facing:"north"}}],
        blocks:[{pos:[1,1,1],state:0,nbt:{id:"minecraft:chest",storage:{items:[{id:"mod:gem",Count:3b}]}}}],
        entities:[
            {pos:[1.25d,1.5d,1.75d],blockPos:[1,1,1],nbt:{id:"mod:creature",UUID:[I;1,2,3,4],
                Pos:[1.25d,1.5d,1.75d],Rotation:[30f,10f],Inventory:[{id:"mod:gem",Count:2b}],custom:{keep:99L},
                Passengers:[{id:"mod:rider",UUID:[I;5,6,7,8],Pos:[1.25d,2.5d,1.75d],Rotation:[0f,0f],custom:{keep:7L}}]}},
            {pos:[2.5d,2.5d,1.03125d],blockPos:[2,2,1],nbt:{id:"minecraft:item_frame",UUID:[I;9,10,11,12],
                TileX:2,TileY:2,TileZ:1,Facing:2b,Item:{id:"mod:gem",Count:1b}}},
            {pos:[4d,1d,1d],blockPos:[4,1,1],nbt:{id:"minecraft:chicken",UUID:[I;13,14,15,16]}},
            {pos:[2d,2d,2d],blockPos:[2,2,2],nbt:{id:"minecraft:player",UUID:[I;17,18,19,20]}}
        ]}''')))


def selection(scene):
    return scene.select(((1, 1, 1), (4, 4, 3)))


def identities(records):
    return [payload["UUID"].to_snbt() for record in records for payload in payloads(record["nbt"])]


def test_capture_keeps_local_coordinates_containers_and_passengers_but_excludes_players(scene):
    clipboard = scene.copy(selection(scene))
    assert clipboard.block_count == 1 and len(clipboard.entities) == 2 and clipboard.excluded_players == 1
    source = clipboard.render_source()
    assert tuple(float(v) for v in source.entities[0]["pos"]) == (0.25, 0.5, 0.75)
    assert source.entities[0]["nbt"]["Passengers"][0]["Pos"] == from_snbt("[0.25d,1.5d,0.75d]")
    assert source.block_nbt[(0, 0, 0)]["storage"] == scene.snapshot().block_nbt[(1, 1, 1)]["storage"]
    source.entities[0]["nbt"]["custom"]["keep"] = from_snbt("0L")
    assert int(clipboard.entities[0][1].unpack()["nbt"]["custom"]["keep"]) == 99
    assert not scene.dirty


@pytest.mark.parametrize("take", [False, True])
@pytest.mark.parametrize("position", [(5, 2, 4), (-4, -2, -3)])
def test_combined_placement_has_one_history_entry_and_lossless_save(scene, tmp_path, take, position):
    before = scene.snapshot()
    clipboard = scene.copy(selection(scene))
    change = scene.paste(clipboard, position, take=take)
    assert change.changes and len(change.entities) == 2 and not scene.dirty
    preview = scene.snapshot(change)
    scene.apply(change)
    assert len(scene.history.entries) == 1
    assert scene.snapshot().entities == preview.entities
    assert scene.snapshot().block_nbt == preview.block_nbt
    after = [delta.after.unpack() for delta in change.entities]
    expected = [shift_entity(record, tuple(p - lo for p, lo in zip(position, selection(scene).lower))) for record in before.entities[:2]]
    for actual, original in zip(after, expected):
        assert actual["pos"] == original["pos"] and actual["blockPos"] == original["blockPos"]
        for current, previous in zip(payloads(actual["nbt"]), payloads(original["nbt"])):
            if not take:
                assert current.pop("UUID") != previous.pop("UUID")
        assert actual == original
    saved = scene.save(tmp_path / "combined.nbt")
    assert Structure(saved).entities == preview.entities
    assert Structure(saved).block_nbt == preview.block_nbt
    scene.undo()
    assert scene.snapshot().entities == before.entities and scene.snapshot().block_nbt == before.block_nbt
    assert scene.size == before.size and scene.origin == (0, 0, 0)
    scene.redo()
    assert scene.snapshot().entities == preview.entities


def test_rotate_and_mirror_keep_frame_anchors_and_entity_heading_aligned(scene):
    clipboard = scene.copy(selection(scene))
    rotated = clipboard.transformed(turns=1)
    record = rotated.entities[0][1].unpack()
    assert rotated.size == (2, 3, 3) and rotated.cells[0][0] == (1, 0, 0)
    assert tuple(float(v) for v in record["pos"]) == (1.25, 0.5, 0.25)
    assert tuple(float(v) for v in record["nbt"]["Rotation"]) == (120, 10)
    frame = rotated.entities[1][1].unpack()
    assert frame["blockPos"] == from_snbt("[1,1,1]") and int(frame["nbt"]["Facing"]) == 5
    mirrored = clipboard.transformed(flip="x")
    assert tuple(float(v) for v in mirrored.entities[0][1].unpack()["pos"]) == (2.75, 0.5, 0.75)
    assert int(mirrored.entities[0][1].unpack()["nbt"]["Rotation"][0]) == 330
    assert mirrored.transformed(flip="x").entities[0] == clipboard.entities[0]
    assert rotated.transformed(turns=3).entities[0] == clipboard.entities[0]
    combined = clipboard.transformed(flip="z", turns=3)
    assert combined.entities == clipboard.transformed(flip="z").transformed(turns=3).entities


@pytest.mark.parametrize("blocks,entities", [(False, True), (True, False)])
def test_content_switches_apply_to_take_and_preserve_unselected_content(scene, blocks, entities):
    before = scene.snapshot()
    change = scene.paste(scene.copy(selection(scene)), (4, 2, 4), take=True, include_blocks=blocks, include_entities=entities)
    assert bool(change.changes) is blocks and bool(change.entities) is entities
    scene.apply(change)
    if not blocks:
        assert scene.snapshot().block_nbt == before.block_nbt
    if not entities:
        assert scene.snapshot().entities == before.entities
    scene.undo()
    assert scene.snapshot().entities == before.entities


def test_entity_only_paste_ignores_block_masks_and_air(scene):
    before = scene.snapshot()
    plan = plan_placement(scene, scene.copy(selection(scene)), ((1, 1, 1),), include_blocks=False,
                          include_air=True, destination=DestinationRule("material", "mod:absent"))
    assert not plan.change.changes and len(plan.change.entities) == 2 and plan.skipped == 0
    assert "2 entities" in plan.summary
    scene.apply(plan.change)
    assert scene.snapshot().block_nbt == before.block_nbt
    assert len(set(identities(scene.snapshot().entities))) == len(identities(scene.snapshot().entities))


def test_stack_and_repeated_paste_give_every_copy_and_passenger_new_ids(scene):
    clipboard = scene.copy(selection(scene))
    scene.apply(scene.stack(selection(scene), 3, (0, 3, 0)))
    assert len(scene._entities) == 10 and len(scene.history.entries) == 1
    scene.apply(scene.paste(clipboard, (1, 1, 1)))
    records = scene.snapshot().entities
    assert len(identities(records)) == len(set(identities(records))) == 17
    scene.undo()
    scene.undo()
    assert len(scene._entities) == 4


def test_cross_document_copy_drops_world_location_and_stale_take_is_rejected(scene, edit):
    key = next(iter(scene._entities))
    scene._entities[key] = replace(scene._entities[key], location=EntityLocation("minecraft:the_nether", "entities", chunk=(9, 8)))
    clipboard = scene.copy(selection(scene))
    with pytest.raises(ValueError, match="fresh"):
        edit.paste(clipboard, (0, 0, 0), take=True)
    change = edit.paste(clipboard, (0, 0, 0))
    assert all(delta.after.location is None for delta in change.entities)
    edit.apply(change)
    edit.undo()
    assert len(edit._entities) == 1


def test_reflected_entity_on_block_edge_can_expand_past_the_clipboard_bounds(scene):
    clipboard = scene.copy(scene.select(((4, 1, 1), (5, 2, 2)))).transformed(flip="x")
    change = scene.paste(clipboard, (7, 1, 1), include_blocks=False)
    assert change.resize.after == (9, 8, 8)
    assert float(change.entities[0].after.unpack()["pos"][0]) == 8
    scene.apply(change)
    scene.undo()
    assert scene.size == (8, 8, 8)


def test_empty_content_and_entity_work_budget_fail_before_uuid_generation(scene, monkeypatch):
    clipboard = scene.copy(selection(scene))
    with pytest.raises(ValueError, match="Choose"):
        scene.paste(clipboard, (0, 0, 0), include_blocks=False, include_entities=False)
    monkeypatch.setattr(scene, "operation_limit", 3)
    with pytest.raises(ValueError, match="budget"):
        plan_placement(scene, clipboard, ((0, 0, 0), (0, 3, 0)), include_blocks=False)
    assert not scene.dirty


@pytest.mark.parametrize("take", [False, True])
def test_sponge_roundtrip_preserves_copied_entities_inventories_and_metadata(scene, tmp_path, take):
    from structura_core.export_schematic import schematic_root
    from structura_core.nbt import write_root
    from structura_core.schematic import Schematic

    root = schematic_root(scene.snapshot())
    root["Metadata"] = from_snbt('{mod:{keep:42L}}')
    path = tmp_path / "original.schem"
    write_root(root, path)
    edit = EditSession.open(path)
    edit.apply(edit.paste(edit.copy(selection(edit)), (-4, 0, -3), take=take))
    edit.save(tmp_path / "placed.schem")
    saved = Schematic(tmp_path / "placed.schem")
    assert saved.root["Metadata"] == root["Metadata"]
    reopened = EditSession.open(tmp_path / "placed.schem").snapshot()
    expected = edit.snapshot()
    assert reopened.entities == expected.entities
    assert reopened.block_nbt == expected.block_nbt
    edit.undo()
    assert edit.snapshot().entities == EditSession.open(path).snapshot().entities


@pytest.mark.parametrize("take", [False, True])
def test_world_combined_change_crosses_chunks_survives_refresh_save_and_undo(tmp_path, take):
    from amulet_nbt import NamedTag
    from amulet.level.formats.anvil_world.region import AnvilRegionInterface
    from structura_core.nbt import write_root
    from structura_core.world import JavaWorld
    from structura_edit.world_view import WorldView

    write_root(from_snbt('{Data:{DataVersion:3955}}'), tmp_path / "level.dat")
    for folder in ("region", "entities"):
        (tmp_path / folder).mkdir()
    chunks = AnvilRegionInterface(str(tmp_path / "region" / "r.0.0.mca"))
    for x, state in ((0, "minecraft:stone"), (1, "minecraft:air")):
        chunks.write_data(x, 0, NamedTag(from_snbt('{DataVersion:3955,xPos:' + str(x) + ',zPos:0,sections:[{Y:0b,block_states:{palette:[{Name:"' + state + '"}]}}]}')))
    chunks.unload()
    entities = AnvilRegionInterface(str(tmp_path / "entities" / "r.0.0.mca"))
    entities.write_data(0, 0, NamedTag(from_snbt('''{DataVersion:3955,Position:[I;0,0],Entities:[
        {id:"mod:mob",UUID:[I;1,2,3,4],Pos:[2d,5d,2d],custom:{energy:5L},
         Passengers:[{id:"mod:rider",UUID:[I;5,6,7,8],Pos:[2d,6d,2d],Items:[{id:"mod:gem",Count:7b}]}]}]}''')))
    entities.unload()
    world = JavaWorld(tmp_path)
    def reopen(changes=None):
        return WorldView(world, world.read_region((8, 8, 8), radius=1, vertical_radius=16), changes)
    edit = reopen()
    def local(position):
        return tuple(p - o for p, o in zip(position, edit.origin))
    original = edit.snapshot().entities
    clipboard = edit.copy(edit.select((local((1, 4, 1)), local((4, 7, 4)))))
    refreshed = WorldView(world, world.read_region((24, 8, 8), radius=1, vertical_radius=16), edit.world_changes)
    with pytest.raises(ValueError, match="fresh"):
        refreshed.paste(clipboard, local((17, 4, 1)), take=True)
    change = edit.paste(clipboard, local((17, 4, 1)), take=take)
    assert change.changes and len(change.entities) == 1
    edit.apply(change)
    edit = reopen(edit.world_changes)
    assert len(edit._entities) == (1 if take else 2)
    edit.save()
    saved = reopen()
    assert sorted(identities(saved.snapshot().entities)) == sorted(identities(edit.snapshot().entities))
    assert saved.state_at(local((17, 4, 1))) == "minecraft:stone"
    edit.undo()
    edit.save()
    restored = reopen()
    assert restored.snapshot().entities == original
    assert restored.state_at(local((17, 4, 1))) == "minecraft:air"
