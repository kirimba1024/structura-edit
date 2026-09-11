import pickle
from copy import deepcopy

import pytest
from amulet_nbt import CompoundTag, IntTag, ListTag, StringTag, from_snbt
from structura_core import Structure
from structura_core.block_array import BlockArray
from structura_core.nbt import load_root, parse_state

from structura_edit import EditSession
from structura_edit.document import Document


@pytest.mark.parametrize('palette_index', [0, 1])
def test_compact_document_roundtrip_preserves_palettes_metadata_and_nbt(structure, tmp_path, palette_index):
    root = deepcopy(structure._root)
    alternative = deepcopy(root['palette'])
    alternative[0] = parse_state('minecraft:dirt')
    root['palettes'] = ListTag([deepcopy(root['palette']), alternative])
    root['blocks'][0]['extra'] = from_snbt('{bytes:[B;1b,-2b],longs:[L;3L],nested:[{value:2.5d}],empty:[]}')
    source = Structure.from_root(root, palette_index)
    session = EditSession.from_structure(source)
    session = pickle.loads(pickle.dumps(session, protocol=5))
    assert load_root(session.save(tmp_path / 'compact.nbt')) == root
    session.apply(session.set_block((0, 0, 0), 'minecraft:glass'))
    session.undo()
    assert load_root(session.save(tmp_path / 'restored.nbt')) == root
    assert source._root == root


def test_compact_document_owns_metadata_containers_and_entities(structure, tmp_path):
    expected = deepcopy(structure._root)
    session = EditSession.from_structure(structure)
    structure._block_records[(0, 0, 0)]['extra'] = StringTag('changed')
    structure._root['custom']['keep'] = StringTag('changed')
    structure.block_nbt[(1, 0, 0)]['Items'][0]['count'] = IntTag(99)
    structure.entities[0]['nbt']['custom'] = StringTag('changed')
    structure.palette_raw[0]['Name'] = StringTag('minecraft:dirt')
    assert load_root(session.save(tmp_path / 'owned.nbt')) == expected


def test_plain_block_storage_is_sparse_and_stays_compact_after_resize(tmp_path):
    blocks = ListTag([CompoundTag({'pos': ListTag([IntTag(x), IntTag(0), IntTag(0)]), 'state': IntTag(0)})
                      for x in range(1024)])
    source = Structure.from_root(CompoundTag({'DataVersion': IntTag(3955), 'size': ListTag([IntTag(1024), IntTag(1), IntTag(1)]),
                                             'palette': ListTag([parse_state('minecraft:stone')]), 'blocks': blocks, 'entities': ListTag()}))
    session = EditSession.from_structure(source)
    encoded = pickle.dumps(session._document.source, protocol=5)
    assert len(encoded) < len(pickle.dumps(source, protocol=5)) / 3
    assert not session._document.source._block_records
    session.apply(session.paste(session.copy(session.select()), (-1024, 0, 0), take=True))
    transferred = pickle.loads(pickle.dumps(session, protocol=5))
    assert not transferred._document.source._block_records
    assert transferred.undo()
    assert load_root(transferred.save(tmp_path / 'restored.nbt')) == source._root


def test_compaction_uses_current_structure_fields(structure, tmp_path):
    structure.present[(0, 1, 0)] = 0
    structure.present[(2, 0, 0)] = 1
    structure.block_nbt[(2, 0, 0)] = deepcopy(structure.block_nbt[(1, 0, 0)])
    structure.entities.clear()
    structure.source_origin = (-8, -16, -32)
    document = Document(structure)
    session = EditSession(document)
    assert session.origin == structure.source_origin
    saved = Structure(session.save(tmp_path / 'current.nbt'))
    assert saved.present == structure.present
    assert saved.block_nbt == structure.block_nbt
    assert saved.entities == []


@pytest.mark.parametrize('array', [False, True])
def test_positive_resize_preserves_branch_data_and_snapshot_ownership(structure, tmp_path, array):
    if array:
        present = BlockArray.empty(structure.size)
        for position, index in structure.present.items():
            present[position] = index
        structure.present = present
    session = EditSession.from_structure(structure)
    original = load_root(session.save(tmp_path / 'original.nbt'))
    branch = session.fork()
    clip = branch.copy(branch.select())
    branch.apply(branch.paste(clip, (branch.size[0], 0, 0)))
    expanded = branch.snapshot()
    expected = load_root(branch.save(tmp_path / 'expanded.nbt'))
    expanded.block_nbt[(1, 0, 0)]['Items'][0]['count'] = IntTag(99)
    expanded.entities[0]['nbt']['custom'] = StringTag('changed')
    expanded.palette_raw[0]['Name'] = StringTag('minecraft:dirt')
    expanded._root['custom']['keep'] = StringTag('changed')
    assert load_root(branch.save(tmp_path / 'independent.nbt')) == expected
    assert load_root(session.save(tmp_path / 'unmodified.nbt')) == original
    assert branch.undo()
    assert load_root(branch.save(tmp_path / 'undo.nbt')) == original
    assert branch.redo()
    assert load_root(branch.save(tmp_path / 'redo.nbt')) == expected
    branch.apply(branch.paste(clip, (-session.size[0], 0, 0)))
    assert branch.undo()
    assert load_root(branch.save(tmp_path / 'rebased-undo.nbt')) == expected
    assert load_root(session.save(tmp_path / 'still-original.nbt')) == original


def test_one_block_expansion_does_not_copy_or_rekey_existing_cells(edit):
    class NoScan(dict):
        def copy(self):
            raise AssertionError('Copied an unchanged block map')

        def items(self):
            raise AssertionError('Scanned an unchanged block map')

    clip = edit.copy(edit.select(((0, 0, 0), (1, 1, 1))))
    change = edit.paste(clip, (edit.size[0], 0, 0), include_entities=False)
    original = edit.size
    base = edit._document.source
    base.present = NoScan(base.present)
    edit._cells = NoScan(edit._cells)
    edit.apply(change)
    assert edit.size == change.resize.after and edit.state_at((original[0], 0, 0)) == 'minecraft:stone'
    assert edit.undo() and edit.size == original
    assert edit.redo() and edit.size == change.resize.after
    assert base.size == original


@pytest.mark.parametrize('protocol', [4, 5])
def test_compact_change_pickle_preserves_shared_cells_nbt_entities_and_resize(edit, protocol, tmp_path):
    from copy import copy

    change = edit.paste(edit.copy(edit.select()), (-5, -3, -8))
    restored = pickle.loads(pickle.dumps(change, protocol=protocol))
    assert restored == change
    assert copy(restored.changes[0]) == restored.changes[0]
    first, second = edit.fork(), edit.fork()
    first.apply(change)
    second.apply(restored)
    assert load_root(first.save(tmp_path / 'first.nbt')) == load_root(second.save(tmp_path / 'second.nbt'))
