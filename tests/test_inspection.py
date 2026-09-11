import pickle

from amulet_nbt import from_snbt
from structura_core import Structure
from structura_edit import EditSession
from structura_edit.inspection import block_details, inspect_selection, PREVIEW_SPAN


def test_block_card_reads_exact_state_and_inventory_without_mutating(edit):
    before = pickle.dumps(edit.snapshot())
    title, facts, detail = block_details(edit, (1, 0, 0))
    assert title == "Chest"
    assert "facing=north" in facts
    assert "Inventory · 3 items · 1 slot" in facts
    assert detail == "minecraft:chest[facing=north]"
    result = inspect_selection(edit, edit.select(((1, 0, 0), (2, 1, 1))))
    assert result['source'].block_nbt[(0, 0, 0)]['Items'][0]['id'] == 'minecraft:diamond'
    assert pickle.dumps(edit.snapshot()) == before


def test_selection_card_counts_buried_blocks_and_pending_changes(edit):
    edit.apply(edit.set_block((0, 1, 0), 'minecraft:gold_block'))
    result = inspect_selection(edit, edit.select())
    assert '3 total · 3 materials' in result['facts']
    assert any('Gold block' in line for line in result['facts'])
    assert len(result['source'].present) == 5
    assert len(result['source'].entities) == 1


def test_entity_card_keeps_custom_name_and_health(edit):
    from structura_edit.entity_data import EntityData

    record = edit._entities['entity:0'].unpack()
    record['nbt'].update(from_snbt('{CustomName: \'{"text":"Test buddy"}\', Health: 12.5f}'))
    edit._entities['entity:0'] = EntityData(record.to_snbt())
    result = inspect_selection(edit, None, ('entity:0',))
    assert result['title'] == 'Test buddy'
    assert 'Health 12.5' in result['facts']
    assert result['source'].entities[0]['nbt']['custom'] == 'keep'
    assert tuple(float(v) for v in result['source'].entities[0]['pos']) == (.5, 0, .5)


def test_large_preview_is_bounded_but_counts_use_original_cells():
    source = Structure.from_root(from_snbt('{DataVersion:3955,size:[256,2,256],palette:[{Name:"minecraft:stone"}],blocks:[],entities:[]}'))
    source.present = {(x, 0, z): 0 for x in range(256) for z in range(256)}
    edit = EditSession.from_structure(source)
    result = inspect_selection(edit, edit.select())
    assert '65,536 total · 1 material' in result['facts']
    assert max(result['source'].size) <= PREVIEW_SPAN
    assert len(result['source'].present) == PREVIEW_SPAN ** 2
    assert 'grouped 8 × 8 × 8' in result['note']
