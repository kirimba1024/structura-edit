from pathlib import Path

import pytest

from structura_edit import CellSet, EditSession
from structura_edit.changes import _Cell
from structura_edit.drafts import list_drafts, restore_draft, save_draft
from structura_edit.fragments import list_fragments, load_fragment, save_fragment
from structura_edit.placement import Placement


def test_draft_recovers_nbt_bounds_saved_delta_without_old_history(edit, tmp_path):
    output = tmp_path / 'source.nbt'
    edit.save(output)
    disk = output.read_bytes()
    edit.apply(edit.paste(edit.copy(edit.select()), (-4, 0, 0)))
    edited = edit.snapshot()
    saved = save_draft(edit, root=tmp_path / 'drafts')
    restored = restore_draft(saved)
    assert restored.dirty and not restored.can_undo
    assert (restored.origin, restored.size) == (edit.origin, edit.size)
    assert restored.snapshot().block_nbt == edited.block_nbt
    assert restored.snapshot().entities == edited.entities
    assert output.read_bytes() == disk
    restored.apply(restored.set_block((0, 0, 0), 'minecraft:diamond_block'))
    assert restored.undo() and restored.state_at((0, 0, 0)) == edit.state_at((0, 0, 0))
    restored.save(tmp_path / 'recovered.nbt')
    assert EditSession.open(tmp_path / 'recovered.nbt').snapshot().block_nbt == edited.block_nbt


def test_world_draft_keeps_global_patch_and_writes_no_world_files(world_edit, tmp_path):
    world_edit.apply(world_edit.set_block((0, 0, 0), 'minecraft:gold_block'))
    world_edit.world_changes.patch[(world_edit.dimension, 1600, 0, 0)] = _Cell('minecraft:stone'), _Cell('minecraft:air')
    saved = save_draft(world_edit, root=tmp_path / 'drafts')
    restored = restore_draft(saved)
    assert restored.world_changes.patch == world_edit.world_changes.patch
    assert restored.state_at((0, 0, 0)) == 'minecraft:gold_block' and not restored.can_undo
    assert not (tmp_path / '.structura').exists()


def test_failed_draft_publish_retains_previous_checkpoint(edit, tmp_path, monkeypatch):
    import structura_edit.local_store as storage
    root = tmp_path / 'drafts'
    first = save_draft(edit, root=root)
    edit.apply(edit.set_block((0, 0, 0), 'minecraft:gold_block'))
    def fail(*args):
        raise OSError('pointer write failed')
    monkeypatch.setattr(storage, 'atomic_write', fail)
    with pytest.raises(OSError, match='pointer'):
        save_draft(edit, root=root)
    assert list_drafts(root)[0]['path'] == str(first)
    assert restore_draft(first).state_at((0, 0, 0)) == 'minecraft:stone'


def test_draft_bounds_and_file_integrity_are_checked(edit, tmp_path):
    saved = save_draft(edit, root=tmp_path / 'drafts')
    (saved / 'patch.json').write_text('{}')
    with pytest.raises(ValueError, match='changed'):
        restore_draft(saved)


@pytest.mark.parametrize('missing', [False, True])
def test_recovered_draft_requires_explicit_save_path_when_source_changed(edit, tmp_path, missing):
    original = edit.save(tmp_path / 'source.nbt')
    edit.apply(edit.set_block((0, 0, 0), 'minecraft:gold_block'))
    draft = save_draft(edit, root=tmp_path / 'drafts')
    if missing:
        original.unlink()
        expected = None
    else:
        other = EditSession.open(original)
        other.apply(other.set_block((0, 0, 0), 'minecraft:diamond_block'))
        other.save()
        expected = original.read_bytes()
    recovered = restore_draft(draft)
    assert recovered.save_target is None and recovered.notices
    with pytest.raises(ValueError, match='Save as'):
        recovered.save()
    assert (original.read_bytes() if original.exists() else None) == expected
    target = tmp_path / 'recovered.nbt'
    recovered.save(target)
    assert recovered.save() == target and not recovered.dirty
    assert EditSession.open(target).state_at((0, 0, 0)) == 'minecraft:gold_block'


def test_fragment_roundtrip_keeps_sparse_air_footprint_anchor_and_nbt(edit, tmp_path):
    selected = CellSet.from_positions([(0, 0, 0), (1, 0, 0), (3, 0, 0)])
    path = save_fragment(edit, selected, 'Doorway', ('stone', 'windows'), (1, 0, 0), root=tmp_path / 'library')
    clipboard = load_fragment(path)
    assert clipboard.footprint.volume == 3 and (2, 0, 0) not in clipboard.footprint
    assert clipboard.anchor == (1, 0, 0) and Placement(clipboard, (0, 0, 0)).anchor == clipboard.anchor
    assert any(cell.keep_nbt for _, cell in clipboard.cells)
    assert list_fragments(tmp_path / 'library')[0]['name'] == 'Doorway'
    assert (Path(path) / 'thumbnail.png').is_file()
    destination = edit.fork()
    destination.apply(destination.fill(destination.select(), 'minecraft:gold_block'))
    destination.apply(destination.paste(clipboard, (0, 0, 0), include_air=True))
    assert destination.state_at((2, 0, 0)) == 'minecraft:gold_block'
    assert destination.snapshot().block_nbt[(1, 0, 0)] == edit.snapshot().block_nbt[(1, 0, 0)]
