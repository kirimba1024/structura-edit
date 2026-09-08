import pytest
from structura_core import Structure


def test_overlap_reads_one_snapshot_and_last_copy_wins(edit):
    source = edit.select(((0, 0, 0), (2, 1, 1)))
    before = edit.snapshot().block_nbt.copy()
    change = edit.stack(source, 3, (1, 0, 0))
    assert not edit.dirty and not edit.can_undo
    edit.apply(change)
    assert [edit.state_at((x, 0, 0)).split("[", 1)[0] for x in range(5)] == ["minecraft:stone"] * 4 + ["minecraft:chest"]
    assert edit.snapshot().block_nbt[(4, 0, 0)] == before[(1, 0, 0)]
    assert len(edit.history.entries) == 1
    edit.undo()
    assert edit.size == (4, 2, 3) and edit.snapshot().block_nbt == before and not edit.dirty
    edit.redo()
    assert edit.state_at((4, 0, 0)).startswith("minecraft:chest")


@pytest.mark.parametrize("step", [(0, -3, 0), (5, 0, 0), (-5, 2, -4)])
def test_stack_expands_once_preserves_container_data_and_roundtrips(edit, tmp_path, step):
    selection = edit.select(((1, 0, 0), (2, 1, 1)))
    payload = edit.snapshot().block_nbt[(1, 0, 0)]
    edit.apply(edit.stack(selection, 3, step))
    for n in range(4):
        position = tuple(p + n * d - o for p, d, o in zip(selection.lower, step, edit.origin))
        assert edit.snapshot().block_nbt[position] == payload
    path = edit.save(tmp_path / "stack.nbt")
    assert Structure(path).block_nbt == edit.snapshot().block_nbt
    assert edit.undo() and edit.size == (4, 2, 3)
    assert len(edit.snapshot().block_nbt) == 1


def test_stack_air_only_clears_copy_cells_and_preserves_gaps(edit):
    edit.apply(edit.set_block((2, 0, 0), "minecraft:glass"))
    edit.apply(edit.set_block((3, 0, 0), "minecraft:gold_block"))
    edit.apply(edit.set_block((2, 1, 0), "minecraft:glass"))
    selection = edit.select(((0, 0, 0), (1, 2, 1)))
    change = edit.stack(selection, 1, (2, 0, 0), include_air=True)
    edit.apply(change)
    assert edit.state_at((2, 0, 0)) == "minecraft:stone"
    assert edit.state_at((2, 1, 0)) == "minecraft:air"
    assert edit.state_at((1, 0, 0)).startswith("minecraft:chest")
    assert edit.state_at((3, 0, 0)) == "minecraft:gold_block"


def test_clipboard_remains_portable_after_negative_resize_and_undo(edit):
    clipboard = edit.copy(edit.select(((1, 0, 0), (2, 1, 1))))
    payload = edit.snapshot().block_nbt[(1, 0, 0)]
    edit.apply(edit.paste(clipboard, (-4, -2, 0), take=True))
    edit.apply(edit.paste(clipboard, (3, 3, 1)))
    assert edit.snapshot().block_nbt[(3, 3, 1)] == payload
    edit.undo()
    edit.undo()
    edit.apply(edit.paste(clipboard, (3, 1, 1)))
    assert edit.snapshot().block_nbt[(3, 1, 1)] == payload


@pytest.mark.parametrize("copies,step", [(0, (0, 1, 0)), (True, (0, 1, 0)), (1.5, (0, 1, 0)), (1, (0, 0, 0))])
def test_invalid_repeat_settings_leave_document_unchanged(edit, copies, step):
    with pytest.raises(ValueError):
        edit.stack(edit.select(), copies, step)
    assert not edit.dirty and not edit.can_undo


def test_repeat_checks_work_budget_before_capturing_source(edit, monkeypatch):
    monkeypatch.setattr(edit, "copy", lambda *_: pytest.fail("Copied before checking budget"))
    with pytest.raises(ValueError, match="budget"):
        edit.stack(edit.select(), 10**12, (1, 0, 0))
