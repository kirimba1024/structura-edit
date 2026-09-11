from structura_edit.changes_view import summary, unsaved_changes
from structura_edit.changes import EntityDelta


def test_saved_baseline_follows_successful_save_and_history(edit, tmp_path):
    path = tmp_path / "saved.nbt"
    edit.apply(edit.set_block((0, 0, 0), "minecraft:gold_block"))
    edit.save(path)
    assert not edit.dirty and summary(unsaved_changes(edit)) == "0 unsaved changes"
    assert edit.undo() and edit.dirty
    assert unsaved_changes(edit)["counts"]["changed"] == 1
    edit.save(path)
    assert not edit.dirty
    assert edit.redo() and edit.dirty
    assert unsaved_changes(edit)["counts"]["changed"] == 1
    edit.save(path)
    assert not edit.dirty


def test_saved_entities_and_resize_survive_undo(edit, tmp_path):
    from structura_edit.entity_data import entity_change

    clipboard = edit.copy(edit.select())
    original = (edit.origin, edit.size)
    edit.apply(edit.paste(clipboard, (-4, 0, 0)))
    edit.save(tmp_path / "expanded.nbt")
    assert not edit.dirty
    assert edit.undo()
    assert (edit.origin, edit.size) == original
    result = unsaved_changes(edit)
    assert result["resized"] and result["entities"] and result["outside"]
    assert edit.redo() and not edit.dirty
    key = next(iter(edit._entities))
    edit.apply(entity_change(edit, "Delete entity", (EntityDelta(key, edit._entities[key], None),)))
    assert unsaved_changes(edit)["entities"] == 1
    assert edit.undo() and not edit.dirty


def test_unsaved_world_changes_include_other_areas(world_edit):
    from structura_edit.changes import _Cell

    state = world_edit.world_changes
    state.patch[(world_edit.dimension, 1600, 0, 0)] = _Cell("minecraft:stone"), _Cell("minecraft:air")
    result = unsaved_changes(world_edit)
    assert result["counts"]["removed"] == 1 and result["outside"] == 1
    assert result["removed"] == ()


def test_fork_does_not_mutate_saved_changes(edit):
    branch = edit.fork()
    branch.apply(branch.set_block((0, 0, 0), "minecraft:gold_block"))
    assert branch.dirty and not edit.dirty


def test_net_zero_edit_is_clean_without_losing_history(edit):
    edit.apply(edit.set_block((0, 0, 0), "minecraft:gold_block"))
    edit.apply(edit.set_block((0, 0, 0), "minecraft:stone"))
    assert not edit.dirty and edit.can_undo
