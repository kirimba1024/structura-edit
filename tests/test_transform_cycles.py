from dataclasses import replace
import pickle

import pytest
from amulet_nbt import from_snbt
from structura_core import Structure

from structura_edit import EditSession
from structura_edit.placement import Placement


@pytest.fixture
def asymmetric():
    source = Structure.from_root(from_snbt('''{DataVersion:3955,size:[2,3,5],palette:[{Name:"minecraft:oak_log"}],
        blocks:[{pos:[1,0,2],state:0,custom:{keep:42L},nbt:{id:"mod:container",data:{a:[B;1b,2b,3b]},Items:[{id:"mod:gem",count:2}]}},
                {pos:[0,2,4],state:0}],
        entities:[{pos:[0.2d,1.125d,2.456d],blockPos:[0,1,2],nbt:{id:"mod:entity",UUID:[I;1,2,3,4],
            Rotation:[-127.123f,8.987f],custom:{keep:42L},Motion:[0.0123d,0d,-0.25d]}}]}'''))
    session = EditSession.from_structure(source)
    return session, replace(session.copy(session.select(((0, 0, 0), source.size))), anchor=(1, 0, 2))


@pytest.mark.parametrize("axis", "xyz")
def test_full_cycles_return_exact_cells_entities_nbt_and_anchor(asymmetric, axis):
    session, clipboard = asymmetric
    original = pickle.dumps(clipboard)
    model = Placement(clipboard, (-8, 7, 11), following=False)
    anchor = tuple(p + a for p, a in zip(model.position, model.anchor))
    for _ in range(4):
        model.set_clipboard(model.clipboard.transformed(turns=1, axis=axis))
        assert tuple(p + a for p, a in zip(model.position, model.anchor)) == anchor
        assert not model.following
    assert pickle.dumps(model.clipboard) == original
    assert model.position == (-8, 7, 11)
    assert pickle.dumps(clipboard.transformed(flip=axis).transformed(flip=axis)) == original
    assert pickle.dumps(clipboard.transformed(turns=1, axis=axis).transformed(turns=-1, axis=axis)) == original
    assert not session.dirty


def test_mixed_operations_return_exact_original_after_worker_serialization(asymmetric):
    _, clipboard = asymmetric
    changed = clipboard
    operations = [dict(turns=1, axis="x"), dict(flip="y"), dict(turns=-1, axis="z"), dict(turns=2, axis="y")]
    for operation in operations:
        changed = pickle.loads(pickle.dumps(changed.transformed(**operation)))
    for operation in reversed(operations):
        inverse = dict(operation)
        if "turns" in inverse:
            inverse["turns"] *= -1
        changed = changed.transformed(**inverse)
    assert pickle.dumps(changed) == pickle.dumps(clipboard)


@pytest.mark.parametrize("axis", "xyz")
def test_transformed_move_save_reload_and_undo_keep_custom_payload(asymmetric, axis, tmp_path):
    session, clipboard = asymmetric
    before = session.snapshot()
    changed = clipboard.transformed(turns=1, axis=axis)
    session.apply(session.paste(changed, (8, 8, 8), take=True))
    after = session.snapshot()
    saved = Structure(session.save(tmp_path / f"{axis}.nbt"))
    assert saved.present == after.present and saved.block_nbt == after.block_nbt
    assert saved.entities == after.entities
    assert saved._block_records[(9, 10, 10) if axis == "x" else (10, 8, 9) if axis == "y" else (8, 8, 10)]["custom"] == from_snbt("{keep:42L}")
    assert session.undo()
    restored = session.snapshot()
    assert restored.present == before.present and restored.block_nbt == before.block_nbt and restored.entities == before.entities


@pytest.mark.parametrize('state', ['minecraft:oak_slab[type=bottom]', 'minecraft:oak_stairs[facing=north,half=bottom,shape=inner_left]'])
def test_vertical_mirror_swaps_supported_top_bottom_state_and_restores_data(edit, state):
    edit.apply(edit.set_block((0, 0, 0), state))
    original = edit.copy(edit.select(((0, 0, 0), (1, 1, 1))))
    mirrored = original.transformed(flip='y')
    assert 'top' in mirrored.cells[0][1].state
    assert mirrored.transformed(flip='y') is original
