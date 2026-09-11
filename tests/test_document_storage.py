import pickle
from copy import deepcopy

import pytest
from amulet_nbt import CompoundTag, IntTag, ListTag, StringTag, from_snbt
from structura_core import Structure
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
