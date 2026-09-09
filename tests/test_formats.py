from copy import deepcopy

import pytest
from amulet_nbt import CompoundTag, IntTag, from_snbt
from structura_core.nbt import load_root, write_root
from structura_core.schematic import Schematic

from structura_edit import EditSession


@pytest.mark.parametrize("version", [2, 3])
def test_sponge_native_metadata_and_entities_survive(version, tmp_path, structure):
    root = from_snbt('''{
        Version: 2, DataVersion: 3955, Width: 2s, Height: 1s, Length: 1s,
        Offset: [I; -29, -64, 700], Metadata: {Name: "Fixture", Extra: 43},
        custom: "keep root", Palette: {"minecraft:stone": 0, "minecraft:chest[facing=north]": 1},
        PaletteMax: 2, BlockData: [B; 0b, 1b],
        BlockEntities: [{Pos: [I; 1, 0, 0], Id: "minecraft:chest", custom: "keep payload"}],
        Entities: [], BiomePalette: {"minecraft:plains": 0}, BiomeData: [B; 0b, 0b]
    }''')
    if version == 3:
        root["Version"] = IntTag(3)
        root["Blocks"] = CompoundTag({"Palette": root.pop("Palette"), "Data": root.pop("BlockData"),
                                      "BlockEntities": from_snbt('[{Pos: [I; 1, 0, 0], Id: "minecraft:chest", outer: "keep wrapper", Data: {custom: "keep payload"}}]'),
                                      "Extension": IntTag(18)})
        root.pop("BlockEntities")
        root.pop("PaletteMax")
        root["Biomes"] = CompoundTag({"Palette": root.pop("BiomePalette"), "Data": root.pop("BiomeData")})
        root = CompoundTag({"Schematic": root, "OuterExtension": IntTag(32)})
    path = tmp_path / f"native-{version}.schem"
    write_root(root, path)
    edit = EditSession.open(path)
    assert edit.origin == (-29, -64, 700)
    native_before = deepcopy(root)
    edit.apply(edit.set_block((0, 0, 0), "minecraft:gold_block"))
    output = edit.save(tmp_path / "edited.schem")
    saved = load_root(output)
    before = native_before.get("Schematic", native_before)
    after = saved.get("Schematic", saved)
    blocks_before = before if version == 2 else before["Blocks"]
    blocks_after = after if version == 2 else after["Blocks"]
    for key in ("Offset", "Metadata", "custom", "Entities", "Version", "DataVersion"):
        assert after[key] == before[key]
    assert blocks_after["BlockEntities"] == blocks_before["BlockEntities"]
    if version == 3:
        assert after["Biomes"] == before["Biomes"]
        assert saved["OuterExtension"] == native_before["OuterExtension"]
        assert blocks_after["Extension"] == blocks_before["Extension"]
    else:
        assert after["BiomeData"] == before["BiomeData"]
        assert after["BiomePalette"] == before["BiomePalette"]
    decoded = Schematic(output).to_structure()
    assert decoded.name_at((0, 0, 0)) == "minecraft:gold_block"
    assert decoded.name_at((1, 0, 0)) == "minecraft:chest"
    edit.apply(edit.move(edit.select(((1, 0, 0), (2, 1, 1))), (-1, 0, 0)))
    moved = load_root(edit.save(output))
    moved = moved.get("Schematic", moved)
    moved_blocks = moved if version == 2 else moved["Blocks"]
    assert tuple(int(v) for v in moved_blocks["BlockEntities"][0]["Pos"]) == (0, 0, 0)
    payload = moved_blocks["BlockEntities"][0]
    if version == 3:
        assert str(payload["outer"]) == "keep wrapper"
        payload = payload["Data"]
    assert str(payload["custom"]) == "keep payload"
    assert edit.undo()
    edit.apply(edit.set_block((1, 0, 0), "minecraft:stone"))
    assert not Schematic(edit.save(output)).to_structure().block_nbt
    edit.undo()
    edit.undo()
    assert load_root(edit.save(output)) == native_before
    from structura_edit.object_edits import block_data, edit_block_data

    payload = block_data(edit, (1, 0, 0))[1]
    payload["custom"] = from_snbt('"edited payload"')
    edit.apply(edit_block_data(edit, (1, 0, 0), payload.to_snbt()))
    clipboard = edit.copy(edit.select(((1, 0, 0), (2, 1, 1))))
    edit.apply(edit.paste(clipboard, (-1, -1, -1)))
    expanded = load_root(edit.save(output))
    expanded = expanded.get("Schematic", expanded)
    records = (expanded if version == 2 else expanded["Blocks"])["BlockEntities"]
    assert len(records) == 2
    for record in records:
        if version == 3:
            assert str(record["outer"]) == "keep wrapper"
        assert str(record.get("Data", record)["custom"]) == "edited payload"
    edit.undo()
    edit.undo()
    assert load_root(edit.save(output)) == native_before
    donor = EditSession.from_structure(structure)
    clipboard = donor.copy(donor.select(((1, 0, 0), (2, 1, 1))))
    edit.apply(edit.paste(clipboard, (0, 0, 0)))
    imported = Schematic(edit.save(output)).to_structure()
    assert imported.block_nbt[(0, 0, 0)]["Items"] == structure.block_nbt[(1, 0, 0)]["Items"]
    assert edit.undo()
    assert load_root(edit.save(output)) == native_before


def test_snbt_save(edit, tmp_path):
    edit.apply(edit.set_block((0, 0, 0), "minecraft:glass"))
    path = edit.save(tmp_path / "edited.snbt")
    assert EditSession.open(path).state_at((0, 0, 0)) == "minecraft:glass"


def test_litematic_is_view_only(structure, tmp_path):
    from structura_core.litematic import export_litematic

    path = tmp_path / "view.litematic"
    export_litematic(structure, path)
    edit = EditSession.open(path)
    assert edit.readonly
    with pytest.raises(ValueError, match="view-only"):
        edit.set_block((0, 0, 0), "minecraft:glass")
    with pytest.raises(ValueError, match="view-only"):
        edit.save(tmp_path / "copy.litematic")


@pytest.mark.parametrize("suffix", [".nbt", ".snbt", ".schem", ".litematic", ".mcstructure"])
def test_shared_open_uses_core_formats_with_the_same_block_coordinates(structure, tmp_path, suffix):
    from structura_core import convert_structure, load_structure, state_key
    from structura_edit import open_source

    if suffix == ".mcstructure":
        pytest.importorskip("amulet")
    path = tmp_path / ("input" + suffix)
    convert_structure(structure, path)
    expected = load_structure(path)
    session = open_source(path)
    assert session.size == expected.size
    assert set(session.positions()) == set(expected.present)
    assert all(session.state_at(position) == state_key(expected.palette_raw[index]) for position, index in expected.present.items())
    assert session.readonly == (suffix in (".litematic", ".mcstructure"))


def test_legacy_open_is_editable_and_saves_normalized_nbt_without_overwriting_source(tmp_path, monkeypatch):
    pytest.importorskip("amulet")
    from structura_core import Structure
    from structura_core.conversion_losses import ConversionWarning
    from structura_edit import open_source

    monkeypatch.setenv("AMULET_LEVEL_CACHE_DIR", str(tmp_path / "cache"))
    path = tmp_path / "legacy.schematic"
    root = from_snbt('''{Width:1s,Height:1s,Length:1s,Materials:"Alpha",Blocks:[B;54b],Data:[B;0b],
        TileEntities:[{id:"minecraft:chest",x:0,y:0,z:0,Items:[{Slot:0b,id:"minecraft:apple",Count:2b}]}],
        Entities:[{id:"mod:creature",Pos:[0.5d,0.5d,0.5d],custom:{value:42L}}]}''')
    write_root(root, path, name="Schematic")
    original = path.read_bytes()
    with pytest.warns(ConversionWarning):
        edit = open_source(path)
    assert not edit.readonly
    assert int(edit.snapshot().block_nbt[(0, 0, 0)]["Items"][0]["Count"]) == 2
    edit.apply(edit.set_block((0, 0, 0), "minecraft:gold_block"))
    with pytest.raises(ValueError, match=".nbt or .snbt"):
        edit.save(path)
    output = edit.save(tmp_path / "edited.nbt")
    saved = Structure(output)
    assert saved.name_at((0, 0, 0)) == "minecraft:gold_block"
    assert int(saved.entities[0]["nbt"]["custom"]["value"]) == 42
    assert path.read_bytes() == original


def test_sponge_v1_requests_missing_version_and_can_be_opened_after_answer(tmp_path, structure):
    from structura_core.export_schematic import schematic_root
    from structura_edit.tasks import execute
    from structura_edit.source_loading import SourceVersionRequired

    root = schematic_root(structure)
    root["Version"] = IntTag(1)
    root.pop("DataVersion")
    path = tmp_path / "sponge-v1.schem"
    write_root(root, path)
    request = execute("open", {"path": str(path)})
    assert isinstance(request, SourceVersionRequired)
    edit = execute("open", dict(request.options, source_data_version=structure.data_version))
    assert edit.readonly and edit.size == structure.size
    assert edit.snapshot().palette_raw == structure.palette_raw
