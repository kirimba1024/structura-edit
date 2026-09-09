import pytest

from structura_edit import EditSession, StaleChangeError
from structura_edit.editor_document import EditorDocument, EditPreview


@pytest.fixture
def document(edit):
    document = EditorDocument()
    document.load(edit)
    document.selected.select_all()
    return document


def test_reopening_same_session_invalidates_preview_and_selection(document, edit):
    token = document.input_token
    preview = EditPreview(edit.set_block((0, 0, 0), "minecraft:glass"))
    assert document.show_preview(preview, token=token)
    document.load(edit)
    assert document.preview is None and document.selected.region is None
    assert not document.show_preview(preview, token=token)


def test_empty_preview_is_distinct_from_no_preview(document, edit):
    preview = EditPreview(edit.set_block((0, 0, 0), "minecraft:stone"))
    assert document.show_preview(preview)
    assert document.pending is not None and not document.pending
    assert document.invalidate()
    assert document.pending is None and not document.invalidate()


def test_session_replacement_preserves_selection_until_extent_changes(document, edit):
    selection = document.selection()
    branch = edit.fork()
    branch.apply(branch.set_block((0, 0, 0), "minecraft:glass"))
    update = document.replace(branch)
    assert update.previous is edit and update.session is branch and not update.resized
    assert document.selection() == selection
    expanded = branch.fork()
    expanded.apply(expanded.paste(expanded.copy(selection), (-1, 0, 0)))
    assert document.replace(expanded).resized
    assert document.selected.region is None and document.selected.size == expanded.size


def test_foreign_or_older_session_is_rejected_without_clearing_preview(document, edit, structure):
    previous = edit.fork()
    updated = edit.fork()
    updated.apply(updated.set_block((0, 0, 0), "minecraft:glass"))
    document.replace(updated)
    preview = EditPreview(updated.set_block((0, 0, 0), "minecraft:gold_block"))
    document.show_preview(preview)
    for invalid in (previous, EditSession.from_structure(structure)):
        with pytest.raises(StaleChangeError):
            document.replace(invalid)
        assert document.session is updated and document.preview is preview


def test_close_rejects_inflight_preview(document, edit):
    token = document.input_token
    document.load(None)
    assert document.session is None and document.selected.region is None
    assert not document.show_preview(EditPreview(edit.set_block((0, 0, 0), "minecraft:glass")), token=token)
