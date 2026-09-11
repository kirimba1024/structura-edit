from copy import deepcopy

import pytest

from structura_edit.edit_workflow import EditWorkflow
from structura_edit.editor_document import EditorDocument
from structura_edit.tasks import execute
from structura_edit.task_protocol import DocumentRequest
from structura_edit.worker_document import document_token


class DeferredTasks:
    def __init__(self):
        self.kind = None
        self.request = None

    @property
    def busy(self):
        return self.request is not None

    def submit(self, kind, callback, **args):
        assert not self.busy
        self.kind = kind
        self.request = callback, args
        return True

    def submit_document(self, command, callback, *, session):
        self.kind = command.kind
        self.request = callback, dict(request=DocumentRequest(document_token(session), deepcopy(command), deepcopy(session)))
        return True

    def complete(self):
        kind, (callback, args) = self.kind, self.request
        self.kind = self.request = None
        if "request" in args:
            request = args['request']
            args = dict(vars(request.command), session=request.snapshot)
        callback(execute(kind, deepcopy(args)))


@pytest.fixture
def workflow(edit):
    document = EditorDocument()
    document.load(edit)
    document.selected.set_bounds((0, 0, 0), (1, 1, 1))
    events = []
    workflow = EditWorkflow(document, DeferredTasks(), previewed=lambda preview: events.append(("preview", preview)),
                            updated=lambda update: events.append(("update", update)))
    return workflow, events


def prepare_fill(workflow):
    assert workflow.prepare("operation", mode="Fill", values={"target": "minecraft:glass"})
    workflow.tasks.complete()
    return workflow.document.preview


def test_preview_then_commit_replaces_session_once_before_notifying_caller(workflow, edit):
    edits, events = workflow
    preview = prepare_fill(edits)
    assert preview.material == "minecraft:glass"
    assert edits.document.session is edit and not edit.dirty
    def completed(session):
        assert edits.document.session is session and edits.document.pending is None
        events.append(("complete", session))
    assert edits.commit(preview.change, completed)
    edits.invalidate()
    assert edits.document.preview is preview
    edits.tasks.complete()
    assert edits.document.session.state_at((0, 0, 0)) == "minecraft:glass"
    assert not edit.dirty and [kind for kind, value in events] == ["preview", "update", "complete"]


@pytest.mark.parametrize('order', [(0, 1), (1, 0)])
def test_independent_same_revision_replies_accept_only_first_without_worker_serialization(edit, order):
    from structura_edit.editor_document import EditPreview

    class ConcurrentReplies:
        busy = False
        kind = None

        def __init__(self):
            self.replies = []

        def submit_document(self, command, callback, *, session):
            branch = session.fork()
            branch.apply(command.change)
            self.replies.append((callback, branch))
            return True

    document = EditorDocument()
    document.load(edit)
    tasks = ConcurrentReplies()
    updates, completed = [], []
    edits = EditWorkflow(document, tasks, previewed=lambda preview: None, updated=updates.append)
    for material in ('minecraft:glass', 'minecraft:gold_block'):
        assert edits.commit(edit.set_block((0, 0, 0), material), completed.append)
    first, second = (tasks.replies[index] for index in order)
    assert (first[1]._id, first[1].revision) == (second[1]._id, second[1].revision)
    assert first[1]._state_id != second[1]._state_id
    first[0](first[1])
    preview = EditPreview(document.session.set_block((0, 0, 0), 'minecraft:diamond_block'))
    assert document.show_preview(preview)
    second[0](second[1])
    assert document.session is first[1] and document.preview is preview
    assert len(updates) == len(completed) == 1
    assert not edit.dirty and edit.history.cursor == 0


@pytest.mark.parametrize("change", ["inputs", "selection", "reopen", "session_revision"])
def test_stale_preview_result_is_ignored(workflow, change):
    edits, events = workflow
    document = edits.document
    edits.prepare("operation", mode="Fill", values={"target": "minecraft:glass"})
    if change == "inputs":
        edits.invalidate()
    elif change == "selection":
        document.selected.set_bounds((1, 0, 0), (2, 1, 1))
    elif change == "reopen":
        document.load(document.session)
    else:
        document.session.apply(document.session.set_block((0, 0, 0), "minecraft:gold_block"))
    edits.tasks.complete()
    assert document.pending is None and not events


def test_recipe_text_change_discards_ready_preview_and_inflight_result(workflow):
    edits, events = workflow
    code = 'edit.apply(edit.fill(selection, "minecraft:glass"))\nprint("preview")'
    edits.prepare("recipe", code=code)
    edits.tasks.complete()
    assert edits.document.preview.output == "preview\n"
    edits.invalidate("recipe")
    assert edits.document.pending is None and events[-1] == ("preview", None)
    edits.prepare("recipe", code=code)
    edits.invalidate("recipe")
    count = len(events)
    edits.tasks.complete()
    assert edits.document.pending is None and len(events) == count


def test_editing_recipe_does_not_discard_unrelated_operation_preview(workflow):
    edits, events = workflow
    preview = prepare_fill(edits)
    edits.invalidate("recipe")
    assert edits.document.preview is preview and len(events) == 1


def test_move_selection_destination_belongs_to_prepared_change(workflow):
    edits, _ = workflow
    values = {"offset": (-1, 0, 0)}
    edits.prepare("operation", mode="Move blocks", values=values)
    edits.tasks.complete()
    preview = edits.document.preview
    values["offset"] = (0, 0, 1)
    assert preview.selection_after == ((0, 0, 0), (1, 1, 1))
    edits.commit(preview.change, lambda session: None)
    edits.tasks.complete()
    assert edits.document.session.origin == (-1, 0, 0)
    assert edits.document.session.state_at((0, 0, 0)) == "minecraft:stone"


def test_result_from_previous_document_cannot_replace_reopened_session(workflow):
    edits, events = workflow
    preview = prepare_fill(edits)
    original = edits.document.session
    edits.commit(preview.change, lambda session: pytest.fail("Old apply callback was called"))
    edits.document.load(original)
    edits.tasks.complete()
    assert edits.document.session is original and not original.dirty
    assert [kind for kind, value in events] == ["preview"]


def test_history_and_save_use_same_session_replacement_path(workflow, tmp_path):
    edits, events = workflow
    preview = prepare_fill(edits)
    edits.commit(preview.change, lambda session: None)
    edits.tasks.complete()
    selection = edits.document.selection()
    assert edits.seek_history(0, lambda session: None)
    edits.tasks.complete()
    assert edits.document.session.state_at((0, 0, 0)) == "minecraft:stone"
    assert edits.document.selection() == selection
    assert edits.seek_history(1, lambda session: None)
    edits.tasks.complete()
    assert edits.save(tmp_path / "edited.nbt", lambda session: None)
    edits.tasks.complete()
    assert not edits.document.session.dirty and edits.document.session.can_undo
    assert [kind for kind, value in events].count("update") == 4


def test_preview_failure_keeps_document_unchanged(workflow):
    edits, events = workflow
    edits.prepare("recipe", code='edit.apply(edit.fill(selection, "minecraft:glass"))\nraise ValueError("failure")')
    with pytest.raises(ValueError, match="failure"):
        edits.tasks.complete()
    assert not edits.document.session.dirty and edits.document.pending is None and not events


def test_busy_preview_and_missing_selection_do_not_start_another_task(workflow):
    edits, _ = workflow
    edits.prepare("operation", mode="Fill", values={"target": "minecraft:glass"})
    assert not edits.prepare("recipe", code="pass")
    edits.tasks.complete()
    edits.document.selected.clear()
    assert not edits.prepare("operation", mode="Fill", values={"target": "minecraft:glass"})


def test_non_preview_task_is_rejected_before_submission(workflow, tmp_path):
    edits, _ = workflow
    path = tmp_path / "unexpected.nbt"
    with pytest.raises(ValueError, match="does not prepare an edit"):
        edits.prepare("save", path=path)
    assert not path.exists() and not edits.tasks.busy


def test_preview_metadata_uses_captured_inputs_even_if_the_caller_mutates_values(workflow):
    edits, _ = workflow
    values = {'target': 'minecraft:glass'}
    edits.prepare('operation', mode='Fill', values=values)
    values['target'] = 'minecraft:gold_block'
    edits.tasks.complete()
    assert edits.document.preview.material == 'minecraft:glass'
    assert edits.document.pending.changes[0].after.state == 'minecraft:glass'
