import pytest
from amulet_nbt import from_snbt
from structura_core.nbt import Structure

from structura_edit.object_edits import block_data, edit_block_data, edit_entity_data, entity_items, transform_entities
from structura_edit.session import EditSession


@pytest.fixture
def objects():
    source = Structure.from_root(from_snbt('''{DataVersion:3955,size:[16,16,16],palette:[{Name:"mod:container"}],
        blocks:[{pos:[2,2,2],state:0,nbt:{id:"mod:container",x:2,y:2,z:2,capabilities:{energy:17L},
            storage:{slots:[{Slot:0b,id:"mod:gem",Count:3b,tag:{quality:0.25f}}]}}}],
        entities:[{pos:[3.5d,3d,3.5d],blockPos:[3,3,3],nbt:{id:"mod:creature",Pos:[3.5d,3d,3.5d],UUID:[I;1,2,3,4],
            Rotation:[0f,0f],Inventory:[{Slot:0b,id:"mod:gem",Count:2b}],custom:{keep:99L}}},
            {pos:[5.5d,3d,3.5d],blockPos:[5,3,3],nbt:{id:"minecraft:chicken",UUID:[I;5,6,7,8]}}]}'''))
    return EditSession.from_structure(source)


def test_unknown_entity_inventory_edit_undo_and_save(objects, tmp_path):
    original = objects.snapshot()
    key = next(entity_items(objects))[0]
    payload = objects._entities[key].unpack()["nbt"]
    payload["Inventory"][0]["Count"] = from_snbt("7b")
    change = edit_entity_data(objects, key, payload.to_snbt())
    assert objects.apply(change) == 1
    saved = objects.snapshot().entities[0]["nbt"]
    assert saved["custom"] == original.entities[0]["nbt"]["custom"]
    assert int(saved["Inventory"][0]["Count"]) == 7
    objects.undo()
    assert objects.snapshot().entities == original.entities
    objects.redo()
    path = tmp_path / "entity.nbt"
    objects.save(path)
    assert Structure(path).entities == objects.snapshot().entities
    with pytest.raises(ValueError, match="changed|fresh"):
        objects.apply(change)


def test_typed_inspector_drafts_apply_without_mutating_inputs(objects):
    from structura_edit.nbt_values import replace_value
    from structura_edit.object_edits import edit_objects, inspect_objects

    key = next(iter(objects._entities))
    records = inspect_objects(objects, keys=(key,)) + inspect_objects(objects, position=(2, 2, 2))
    originals = [record["root"].to_snbt() for record in records]
    entity = replace_value(records[0]["root"], ("Inventory", 0, "Count"), from_snbt("9b"))
    block = replace_value(records[1]["root"], ("data", "storage", "slots", 0, "Count"), from_snbt("11b"))
    drafts = [entity.to_snbt(), block.to_snbt()]
    change = edit_objects(objects, [(records[0], entity), (records[1], block)])
    assert [record["root"].to_snbt() for record in records] == originals
    assert [entity.to_snbt(), block.to_snbt()] == drafts
    objects.apply(change)
    assert int(objects._entities[key].unpack()["nbt"]["Inventory"][0]["Count"]) == 9
    assert int(block_data(objects, (2, 2, 2))[1]["storage"]["slots"][0]["Count"]) == 11
    objects.undo()
    restored = inspect_objects(objects, keys=(key,)) + inspect_objects(objects, position=(2, 2, 2))
    assert [record["root"].to_snbt() for record in restored] == originals


def test_entity_group_transform_and_duplicate_identity(objects):
    keys = tuple(objects._entities)
    original = objects.snapshot().entities
    objects.apply(transform_entities(objects, keys, action="Move", offset=(1.25, 2, -1)))
    assert tuple(float(v) for v in objects.snapshot().entities[0]["pos"]) == (4.75, 5, 2.5)
    objects.apply(transform_entities(objects, keys, action="Rotate", angle=90))
    positions = [tuple(float(v) for v in record["pos"]) for record in objects.snapshot().entities]
    assert positions[0] == pytest.approx((5.75, 5, 1.5))
    assert positions[1] == pytest.approx((5.75, 5, 3.5))
    objects.apply(transform_entities(objects, keys, action="Duplicate", offset=(2, 0, 0)))
    assert len(objects._entities) == 4
    uuids = [record["nbt"]["UUID"].to_snbt() for record in objects.snapshot().entities]
    assert len(set(uuids)) == 4
    objects.undo()
    objects.undo()
    objects.undo()
    assert objects.snapshot().entities == original
    objects.apply(transform_entities(objects, keys, action="Delete"))
    assert not objects.snapshot().entities
    objects.undo()
    assert objects.snapshot().entities == original


def test_block_inventory_preserves_mod_tags_types_and_history(objects, tmp_path):
    state, payload = block_data(objects, (2, 2, 2))
    payload["storage"]["slots"][0]["Count"] = from_snbt("11b")
    change = edit_block_data(objects, (2, 2, 2), payload.to_snbt())
    objects.apply(change)
    assert objects.state_at((2, 2, 2)) == state
    assert objects.snapshot().block_nbt[(2, 2, 2)]["capabilities"] == payload["capabilities"]
    objects.undo()
    assert int(block_data(objects, (2, 2, 2))[1]["storage"]["slots"][0]["Count"]) == 3
    objects.redo()
    objects.save(tmp_path / "blocks.snbt")
    assert Structure(tmp_path / "blocks.snbt").block_nbt == objects.snapshot().block_nbt


def test_entity_transactions_and_selection_do_not_mutate_source(objects):
    branch = objects.fork()
    keys = tuple(objects._entities)
    branch.apply(transform_entities(branch, keys, action="Delete"))
    assert len(objects._entities) == 2
    change = objects.diff(branch)
    objects.apply(change)
    assert not objects._entities
    objects.undo()
    assert len(list(entity_items(objects, objects.select(((3, 3, 3), (4, 4, 4)))))) == 1
    change = transform_entities(objects, keys, offset=(100, 0, 0))
    assert change.resize is not None and objects.size == (16, 16, 16)
    objects.apply(change)
    assert objects.size == (106, 16, 16)
    objects.undo()
    assert objects.size == (16, 16, 16)


def test_selection_worker_filters_positions_and_all_selection_does_not_parse_nbt(objects, monkeypatch):
    from structura_edit.entity_data import EntityData
    from structura_edit.tasks import execute
    from structura_edit.object_edits import select_entities

    region = objects.select(((3, 3, 3), (4, 4, 4)))
    keys = execute("objects", dict(session=objects, operation="select", selection=region))
    assert keys == (next(iter(objects._entities)),)
    def unexpected_parse(self):
        raise AssertionError("Selecting all entities must not parse inventories")
    monkeypatch.setattr(EntityData, "unpack", unexpected_parse)
    assert select_entities(objects) == tuple(objects._entities)


@pytest.mark.parametrize("with_uuid", [True, False])
def test_world_entity_changes_survive_refresh_save_and_undo(tmp_path, with_uuid):
    from structura_core.nbt import write_root
    from structura_core.world import JavaWorld
    from structura_edit.world_view import WorldView
    from amulet_nbt import NamedTag
    from amulet.level.formats.anvil_world.region import AnvilRegionInterface

    write_root(from_snbt('{Data:{DataVersion:3955}}'), tmp_path / "level.dat")
    for name, root in (("region", '{DataVersion:3955,xPos:0,zPos:0,sections:[{Y:0b,block_states:{palette:[{Name:"minecraft:stone"}]}}]}'),
                       ("entities", '{DataVersion:3955,Position:[I;0,0],Entities:[{id:"mod:mob",UUID:[I;1,2,3,4],Pos:[2d,5d,2d],custom:{energy:5L}}]}')):
        (tmp_path / name).mkdir()
        region = AnvilRegionInterface(str(tmp_path / name / "r.0.0.mca"))
        root = from_snbt(root)
        if name == "entities" and not with_uuid:
            root["Entities"][0].pop("UUID")
        region.write_data(0, 0, NamedTag(root))
        region.unload()
    world = JavaWorld(tmp_path)
    def reopen(changes=None):
        return WorldView(world, world.read_region((0, 8, 0), radius=0, vertical_radius=16), changes)
    session = reopen()
    key = next(iter(session._entities))
    session.apply(transform_entities(session, [key], offset=(3, 0, 0)))
    assert session.dirty
    session = reopen(session.world_changes)
    assert len(session._entities) == 1
    assert float(session._entities[key].unpack()["pos"][0]) == 5
    session.save()
    assert not session.dirty
    session = reopen(session.world_changes)
    assert len(session._entities) == 1
    assert float(next(iter(session._entities.values())).unpack()["pos"][0]) == 5
    session.undo()
    assert session.dirty and float(session._entities[key].unpack()["pos"][0]) == 2
    session.save()
    assert float(reopen()._entities[key].unpack()["pos"][0]) == 2


@pytest.mark.parametrize("position", [(-3, -2, -4), (16, 16, 16)])
def test_paste_expands_schematic_with_inventory_entities_and_reversible_history(objects, position, tmp_path):
    before = objects.snapshot()
    objects.apply(objects.set_block((1, 1, 1), "minecraft:gold_block"))
    clipboard = objects.copy(objects.select(((2, 2, 2), (3, 3, 3))))
    change = objects.paste(clipboard, position)
    assert change.resize is not None
    preview = objects.snapshot(change)
    assert objects.size == before.size
    objects.apply(change)
    assert objects.snapshot().present == preview.present
    offset = change.resize.offset
    destination = tuple(p + d for p, d in zip(position, offset))
    assert objects.state_at(destination) == "mod:container"
    assert int(block_data(objects, destination)[1]["storage"]["slots"][0]["Count"]) == 3
    assert tuple(objects.origin) == tuple(-v for v in offset)
    assert tuple(float(v) for v in objects.snapshot().entities[0]["pos"]) == tuple(float(v) + d for v, d in zip(before.entities[0]["pos"], offset))
    objects.save(tmp_path / "expanded.nbt")
    assert Structure(tmp_path / "expanded.nbt").size == objects.size
    objects.undo()
    assert objects.size == before.size and objects.origin == (0, 0, 0)
    assert objects.state_at((1, 1, 1)) == "minecraft:gold_block"
    objects.undo()
    assert objects.snapshot().present == before.present and objects.snapshot().entities == before.entities
    objects.redo()
    objects.redo()
    assert objects.snapshot().block_nbt == preview.block_nbt


def test_sponge_expansion_preserves_inventory_entities_and_unknown_metadata(objects, tmp_path):
    from structura_core.export_schematic import schematic_root
    from structura_core.nbt import write_root
    from structura_core.schematic import Schematic

    path = tmp_path / "source.schem"
    root = schematic_root(objects.snapshot())
    root["Metadata"] = from_snbt('{mod:{keep:42L}}')
    root["BiomePalette"] = from_snbt('{"minecraft:plains":0,"minecraft:desert":1}')
    root["BiomeData"] = from_snbt('[B;' + ','.join(str(i % 2) + 'b' for i in range(256)) + ']')
    write_root(root, path)
    edit = EditSession.open(path)
    clip = edit.copy(edit.select(((2, 2, 2), (3, 3, 3))))
    edit.apply(edit.paste(clip, (-2, -1, -3)))
    saved = tmp_path / "expanded.schem"
    edit.save(saved)
    native = Schematic(saved)
    source = native.to_structure()
    assert source.size == edit.size and native.offset == edit.origin
    assert source.block_nbt == edit.snapshot().block_nbt
    assert native.root["Metadata"] == root["Metadata"]
    assert len(native.root["BiomeData"]) == source.size[0] * source.size[2]
    assert tuple(float(v) for v in source.entities[0]["pos"]) == tuple(float(v) for v in edit.snapshot().entities[0]["pos"])


def test_transaction_combines_negative_expansion_blocks_and_entities(objects):
    before = objects.snapshot()
    keys = tuple(objects._entities)
    with objects.transaction("Expand together") as branch:
        branch.apply(branch.paste(branch.copy(branch.select(((2, 2, 2), (3, 3, 3)))), (-2, 0, 0)))
        branch.apply(transform_entities(branch, keys, offset=(0, -5, 0)))
    assert len(objects.history.entries) == 1 and objects.origin == (-2, -2, 0)
    assert objects.state_at((0, 2, 0)) == "mod:container"
    objects.undo()
    assert objects.snapshot().present == before.present and objects.snapshot().entities == before.entities
    objects.redo()
    assert objects.origin == (-2, -2, 0)
