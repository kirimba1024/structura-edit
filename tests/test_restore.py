from structura_edit.changes_view import summary, unsaved_changes


def test_unsaved_changes_kinds(edit):
    result = unsaved_changes(edit)
    assert result["counts"] == {"changed": 0, "added": 0, "removed": 0}
    assert result["outlined"] and summary(result) == "0 unsaved changes"
    edit.apply(edit.set_block((0, 0, 0), "minecraft:gold_block"))
    edit.apply(edit.set_block((0, 1, 0), "minecraft:torch"))
    edit.apply(edit.set_block((1, 0, 0), "minecraft:air"))
    result = unsaved_changes(edit)
    assert result["changed"] == ((0, 0, 0),)
    assert result["added"] == ((0, 1, 0),)
    assert result["removed"] == ((1, 0, 0),)
    assert "3 unsaved changes" in summary(result)


def test_outline_limit_hides_boxes(edit):
    edit.apply(edit.fill(edit.select(((0, 0, 0), (4, 2, 3))), "minecraft:gold_block"))
    from unittest.mock import patch

    with patch("structura_edit.changes_view.OUTLINE_LIMIT", 4):
        result = unsaved_changes(edit)
    assert not result["outlined"] and result["changed"]
    assert "outline hidden" in summary(result)


def test_conflicts_dialog_lists_rows(qt_app):
    from structura_edit.restore_ui import ConflictsDialog

    dialog = ConflictsDialog(None, [((0, 64, 0), "minecraft:stone", "minecraft:dirt", "minecraft:glass")])
    assert dialog.table.rowCount() == 1
    assert dialog.table.item(0, 2).text() == "minecraft:dirt"
    assert dialog.table.item(0, 0).text() == "0 64 0"
    dialog.deleteLater()
