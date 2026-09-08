import json

from PIL import Image

from structura_edit.selection_stats import selection_materials


def test_counts_group_states_respect_bounds_edits_and_resource_textures(edit, tmp_path):
    for directory in ("blockstates", "models/block", "textures/block"):
        (tmp_path / directory).mkdir(parents=True)
    (tmp_path / "blockstates/stone.json").write_text(json.dumps({"variants": {"": {"model": "minecraft:block/stone"}}}))
    model = {"textures": {"all": "minecraft:block/stone"}, "elements": [
        {"from": [0, 0, 0], "to": [16, 16, 16], "faces": {"north": {"texture": "#all"}}}]}
    (tmp_path / "models/block/stone.json").write_text(json.dumps(model))
    Image.new("RGBA", (16, 16), (12, 34, 56, 255)).save(tmp_path / "textures/block/stone.png")
    edit.apply(edit.set_block((2, 0, 0), "minecraft:chest[facing=south]"))
    edit.apply(edit.set_block((0, 1, 0), "minecraft:gold_block"))
    selection = edit.select(((0, 0, 0), (4, 1, 1)))
    rows = selection_materials(edit, selection, tmp_path)
    assert [(name, count) for name, count, _, _ in rows] == [("minecraft:chest", 2), ("minecraft:stone", 1)]
    assert rows[0][2] is None
    assert rows[1][2] == bytes((12, 34, 56, 255)) * 256
    assert not selection_materials(edit, edit.select(((0, 0, 1), (1, 1, 2))), tmp_path)
    edit.undo()
    edit.undo()
    assert [(name, count) for name, count, _, _ in selection_materials(edit, selection, tmp_path)] == [
        ("minecraft:chest", 1), ("minecraft:stone", 1)]
