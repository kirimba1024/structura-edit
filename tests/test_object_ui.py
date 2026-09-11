from types import SimpleNamespace

import pytest

from structura_edit.editor_document import EditorDocument
from structura_edit.object_ui import ObjectController


@pytest.mark.parametrize('change_document', ['reopen', 'edit', 'close'])
def test_late_object_result_is_ignored_after_document_changes(edit, change_document):
    document = EditorDocument()
    document.load(edit)
    pending, received = [], []
    controller = SimpleNamespace(document=document, tasks=SimpleNamespace(
        submit=lambda kind, callback, **args: pending.append(callback)))
    ObjectController._submit(controller, 'inspect', received.append)
    if change_document == 'edit':
        edit.apply(edit.set_block((0, 0, 0), 'minecraft:gold_block'))
    else:
        document.load(edit if change_document == 'reopen' else None)
    pending.pop()(['outdated inventory'])
    assert not received


def test_inspector_rejects_another_document_with_the_same_revision(edit, structure):
    from structura_edit import EditSession

    document = EditorDocument()
    document.load(edit)
    token = document.session_token
    messages = []
    controller = SimpleNamespace(document=document, available=lambda: True,
                                 dialog=SimpleNamespace(errors=SimpleNamespace(setText=messages.append)))
    document.load(EditSession.from_structure(structure))
    ObjectController._edit(controller, token, [])
    assert messages == ['Document changed; reopen the inspector']


@pytest.mark.parametrize('outcome', ['apply', 'stale', 'closed'])
def test_inspector_waits_for_background_work_without_applying_stale_data(edit, outcome):
    document = EditorDocument()
    document.load(edit)
    messages, submitted, enabled = [], [], []
    controller = SimpleNamespace(document=document, available=lambda: True, pending_edit=None,
                                 tasks=SimpleNamespace(busy=True),
                                 edit_timer=SimpleNamespace(start=lambda: None, stop=lambda: None),
                                 dialog=SimpleNamespace(errors=SimpleNamespace(setText=messages.append),
                                     apply=SimpleNamespace(setEnabled=enabled.append),
                                     tabs=SimpleNamespace(setEnabled=enabled.append)),
                                 _submit=lambda operation, callback, **args: submitted.append(args['edits']),
                                 _prepared=lambda change: None)
    controller._edit = lambda *args: ObjectController._edit(controller, *args)
    edits = [('inventory', 'new value')]
    controller._edit(document.session_token, edits)
    assert controller.pending_edit and not submitted and enabled == [False, False]
    ObjectController._flush_edit(controller)
    assert not submitted
    if outcome == 'stale':
        edit.apply(edit.set_block((0, 0, 0), 'minecraft:gold_block'))
    elif outcome == 'closed':
        controller.dialog = None
    controller.tasks.busy = False
    ObjectController._flush_edit(controller)
    assert submitted == ([edits] if outcome == 'apply' else [])
    assert controller.pending_edit is None
    if outcome == 'stale':
        assert messages[-1] == 'Document changed; reopen the inspector'
