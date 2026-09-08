from dataclasses import replace

import pytest
from amulet_nbt import from_snbt
from structura_core import Structure

from structura_edit import EditSession
from structura_edit.object_search import ObjectSearch, PAGE_SIZE
from structura_edit.object_edits import edit_block_data, transform_entities


def test_search_matches_ids_words_and_states_without_empty_cells(edit):
    page = edit.find_objects()
    assert page.total == 3
    assert [row.kind for row in page.rows] == ["entity", "block", "block"]
    assert edit.find_objects("ARMOR_STAND").rows == edit.find_objects("armor stand").rows
    assert edit.find_objects("minecraft:chest north").rows[0].position == (1, 0, 0)
    assert edit.find_objects("air").total == 0
    assert edit.find_objects("missing").rows == ()
    assert edit.find_objects(kind="blocks").total == 2
    assert edit.find_objects(kind="data").rows[0].identity.startswith("minecraft:chest")


def test_search_tracks_added_changed_and_deleted_data_and_undo(edit):
    search = ObjectSearch()
    original = search.find(edit)
    blocks = search.blocks
    assert search.find(edit, "chest").total == 1 and search.blocks is blocks
    edit.apply(edit.set_block((0, 0, 0), "my_mod:storage_crate"))
    edit.apply(edit_block_data(edit, (0, 0, 0), '{custom:{slots:[{id:"my_mod:gem",Count:1b}]}}'))
    assert search.find(edit, "MY_MOD:", kind="data").rows[0].position == (0, 0, 0)
    assert search.blocks is not blocks
    edit.apply(edit.set_block((1, 0, 0), "minecraft:air"))
    assert search.find(edit, "chest").total == 0
    edit.undo()
    edit.undo()
    edit.undo()
    assert search.find(edit) == original


def test_entity_search_uses_current_positions_and_half_open_selection(edit):
    search = ObjectSearch()
    key = next(iter(edit._entities))
    row = search.find(edit, kind="entities").rows[0]
    assert row.key == key and search.blocks is None
    assert search.find(edit, selection=edit.select(((0, 0, 0), (2, 1, 2)))).total == 2
    edit.apply(transform_entities(edit, [key], offset=(1, 0, 0)))
    assert search.find(edit, kind="entities").rows[0].position == (2.5, 1.0, 1.5)
    assert search.find(edit, kind="entities", selection=edit.select(((0, 0, 0), (2, 2, 3)))).total == 0


def test_pagination_has_no_duplicates_and_retains_fractional_entities_before_blocks():
    source = Structure.from_root(from_snbt('{DataVersion:3955,size:[160,2,2],palette:[{Name:"mod:machine"}],blocks:[],entities:[]}'))
    source.present = {(x, 0, 0): 0 for x in range(150)}
    edit = EditSession.from_structure(source)
    search = ObjectSearch()
    pages = [search.find(edit, offset=offset) for offset in range(0, 150, PAGE_SIZE)]
    assert [len(page.rows) for page in pages] == [64, 64, 22]
    assert all(page.total == 150 for page in pages)
    assert len({row.position for page in pages for row in page.rows}) == 150
    assert search.find(edit, offset=200).rows == ()


def test_index_belongs_to_document_origin_dimension_and_revision(edit):
    search = ObjectSearch()
    search.find(edit)
    for change in (lambda: setattr(edit._document, "origin", (-100, -64, -100)),
                   lambda: setattr(edit, "dimension", "mod:dimension")):
        before = search.blocks
        change()
        search.find(edit)
        assert search.blocks is not before
    copy = EditSession.from_structure(edit.snapshot())
    copy.apply(copy.set_block((0, 0, 0), "mod:different"))
    assert search.find(copy, "different").total == 1
    assert search.find(edit, "different").total == 0


def test_block_budget_does_not_prevent_entity_only_search(edit, monkeypatch):
    monkeypatch.setattr("structura_edit.object_search.MAX_INDEX_BYTES", 16)
    search = ObjectSearch()
    with pytest.raises(ValueError, match="reduce the loaded area"):
        search.find(edit, kind="blocks")
    monkeypatch.setattr("structura_edit.object_search.MAX_INDEX_BYTES", 1024)
    assert search.find(edit, kind="entities").total == 1
    assert search.blocks is None


@pytest.mark.parametrize("options", [{"kind": "invented"}, {"limit": 65}, {"limit": 0}, {"offset": -1}, {"offset": True}, {"text": "x" * 257}])
def test_search_rejects_unbounded_or_invalid_queries(edit, options):
    with pytest.raises(ValueError):
        edit.find_objects(**options)


def test_search_is_read_only_and_preserves_player_and_mod_data(edit):
    key, data = next(iter(edit._entities.items()))
    record = data.unpack()
    record["nbt"]["id"] = from_snbt('"mod:odd_creature"')
    edit._entities[key] = replace(data, record=record.to_snbt())
    before = edit.snapshot()
    assert edit.find_objects("mod:").rows[0].key == key
    after = edit.snapshot()
    assert (after.present, after.block_nbt, after.entities) == (before.present, before.block_nbt, before.entities)
    assert not edit.dirty and not edit.can_undo
