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
    update = document.replace(branch, token=document.session_token)
    assert update.previous is edit and update.session is branch and not update.resized
    assert document.selection() == selection
    expanded = branch.fork()
    expanded.apply(expanded.paste(expanded.copy(selection), (-1, 0, 0)))
    assert document.replace(expanded, token=document.session_token).resized
    assert document.selected.region is None and document.selected.size == expanded.size


def test_foreign_or_older_session_is_rejected_without_clearing_preview(document, edit, structure):
    previous = edit.fork()
    updated = edit.fork()
    updated.apply(updated.set_block((0, 0, 0), "minecraft:glass"))
    document.replace(updated, token=document.session_token)
    preview = EditPreview(updated.set_block((0, 0, 0), "minecraft:gold_block"))
    document.show_preview(preview)
    for invalid in (previous, EditSession.from_structure(structure)):
        with pytest.raises(StaleChangeError):
            document.replace(invalid, token=document.session_token)
        assert document.session is updated and document.preview is preview


def test_close_rejects_inflight_preview(document, edit):
    token = document.input_token
    document.load(None)
    assert document.session is None and document.selected.region is None
    assert not document.show_preview(EditPreview(edit.set_block((0, 0, 0), "minecraft:glass")), token=token)


@pytest.mark.parametrize('order', [(0, 1), (1, 0)])
def test_model_accepts_only_one_branch_for_a_captured_version(document, edit, order):
    token = document.session_token
    branches = []
    for material in ('minecraft:glass', 'minecraft:gold_block'):
        branch = edit.fork()
        branch.apply(branch.set_block((0, 0, 0), material))
        branches.append(branch)
    first, late = (branches[index] for index in order)
    assert first._id == late._id and first.revision == late.revision
    assert document.replace(first, token=token).session is first
    preview = EditPreview(first.set_block((1, 0, 0), 'minecraft:diamond_block'))
    document.show_preview(preview)
    selection, current = document.selection(), document.input_token
    assert document.replace(late, token=token) is None
    assert document.replace(first, token=token) is None
    assert document.session is first and document.preview is preview
    assert document.selection() == selection and document.input_token == current


@pytest.mark.parametrize('transition', ['close', 'reopen', 'apply', 'state_id'])
def test_stale_replacement_never_mutates_document(document, edit, transition):
    token = document.session_token
    branch = edit.fork()
    branch.apply(branch.set_block((0, 0, 0), 'minecraft:glass'))
    if transition == 'close':
        document.load(None)
    elif transition == 'reopen':
        document.load(edit)
    elif transition == 'apply':
        edit.apply(edit.set_block((1, 0, 0), 'minecraft:gold_block'))
    else:
        edit._state_id = 'independent state with the same revision'
    current = document.input_token
    assert document.replace(branch, token=token) is None
    assert document.input_token == current


def test_input_changes_do_not_discard_an_inflight_committed_edit(document, edit):
    token = document.session_token
    branch = edit.fork()
    branch.apply(branch.set_block((0, 0, 0), 'minecraft:glass'))
    document.selected.set_bounds((1, 0, 0), (2, 1, 1))
    document.invalidate()
    selection = document.selection()
    assert document.replace(branch, token=token).session is branch
    assert document.selection() == selection
